// ============================================================
// Aphelion Research — Hydra Evolution Engine Implementation
//
// Searches HydraExecutionParams space using tournament selection,
// uniform crossover, and Gaussian mutation.  Uses run_replay_v3
// with HydraStrategy for evaluation — same hot path as the
// standard evolution engine.
// ============================================================

#include "aphelion/hydra_evolution.h"
#include "aphelion/replay_engine.h"
#include "aphelion/account.h"
#include "aphelion/execution.h"
#include "aphelion/reporting.h"
#include "aphelion/robustness_validator.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <filesystem>

namespace fs = std::filesystem;

namespace aphelion {

// ════════════════════════════════════════════════════════════
//  CONSTRUCTOR
// ════════════════════════════════════════════════════════════

HydraEvolutionEngine::HydraEvolutionEngine(
    const HydraEvolutionConfig& config,
    const BarTape& bar_tape,
    const HydraSignalTape& signal_tape
)
    : config_(config)
    , bar_tape_(bar_tape)
    , signal_tape_(signal_tape)
    , rng_(config.random_seed)
{
    if (config_.checkpoint_enabled) {
        fs::create_directories(config_.output_dir);
    }
}


// ════════════════════════════════════════════════════════════
//  MAIN LOOP
// ════════════════════════════════════════════════════════════

void HydraEvolutionEngine::run() {
    auto t_start = std::chrono::high_resolution_clock::now();

    std::cout << "\n================================================================" << std::endl;
    std::cout << " HYDRA EXECUTION PARAMETER EVOLUTION" << std::endl;
    std::cout << " Population: " << config_.population_size << std::endl;
    std::cout << " Generations: " << config_.generations << std::endl;
    std::cout << " Elite count: " << config_.elite_count << std::endl;
    std::cout << " Mutation rate: " << config_.mutation_rate << std::endl;
    std::cout << " Crossover rate: " << config_.crossover_rate << std::endl;
    std::cout << " Min monthly return: " << (config_.min_monthly_return * 100) << "%" << std::endl;
    std::cout << " Max drawdown limit: " << (config_.max_drawdown_limit * 100) << "%" << std::endl;
    std::cout << " Signal bars: " << signal_tape_.size() << std::endl;
    std::cout << " Bar count: " << bar_tape_.bars.size() << std::endl;
    std::cout << "================================================================\n" << std::endl;

    initialize_population();

    for (int gen = 0; gen < config_.generations; ++gen) {
        auto gen_start = std::chrono::high_resolution_clock::now();

        evaluate_population();

        // Compute composites and threshold flags
        for (auto& s : scores_) {
            s.composite_score = compute_composite(s);
            s.passes_threshold =
                !s.liquidated &&
                s.monthly_return >= config_.min_monthly_return &&
                s.max_drawdown  <= config_.max_drawdown_limit &&
                s.profit_factor >= config_.min_profit_factor &&
                s.trade_count   >= config_.min_trade_count;
        }

        // Console summary
        int passing = 0;
        double best_ret = -1e9, best_comp = -1e9;
        for (const auto& s : scores_) {
            if (s.passes_threshold) passing++;
            best_ret  = std::max(best_ret,  s.monthly_return);
            best_comp = std::max(best_comp, s.composite_score);
        }

        auto gen_end = std::chrono::high_resolution_clock::now();
        double gen_secs = std::chrono::duration<double>(gen_end - gen_start).count();

        std::cout << "[gen " << std::setw(4) << gen << "] "
                  << std::fixed << std::setprecision(2) << gen_secs << "s  "
                  << "best_ret=" << std::setprecision(1) << (best_ret * 100) << "% "
                  << "best_comp=" << std::setprecision(3) << best_comp << " "
                  << "passing=" << passing << "/" << scores_.size()
                  << std::endl;

        if (config_.checkpoint_enabled && gen > 0 && gen % config_.checkpoint_interval == 0) {
            write_generation_summary(gen);
        }

        if (gen < config_.generations - 1) {
            select_and_reproduce();
        }
    }

    // Robustness evaluation on top-k
    if (config_.enable_robustness && !scores_.empty()) {
        std::cout << "\n[hydra_evo] Robustness evaluation on top "
                  << config_.robustness_top_k << " candidates..." << std::endl;

        std::sort(scores_.begin(), scores_.end(),
            [](const auto& a, const auto& b) {
                return a.composite_score > b.composite_score;
            });

        int k = std::min(config_.robustness_top_k, static_cast<int>(scores_.size()));

        // Robustness validator expects a StrategyGenome; we can only do a
        // simplified walk-forward by re-evaluating on time windows.
        // Use a lightweight multi-window approach based on the signal tape.
        for (int i = 0; i < k; ++i) {
            // Simple walk-forward: evaluate on three equal-sized windows
            size_t n = bar_tape_.bars.size();
            size_t window = n / 3;
            double scores_arr[3] = {0, 0, 0};
            bool any_valid = false;
            for (int w = 0; w < 3; ++w) {
                size_t start = w * window;
                size_t end   = (w == 2) ? n : (start + window);
                if (end <= start) continue;

                // Build a sub-tape
                HydraSignalTape sub_tape;
                sub_tape.signals.assign(
                    signal_tape_.signals.begin() + start,
                    signal_tape_.signals.begin() + end
                );
                BarTape sub_bar;
                sub_bar.bars.assign(
                    bar_tape_.bars.begin() + start,
                    bar_tape_.bars.begin() + end
                );
                sub_bar.symbol = bar_tape_.symbol;
                sub_bar.timeframe = bar_tape_.timeframe;
                sub_bar.timeframe_seconds = bar_tape_.timeframe_seconds;

                HydraStrategy strat(sub_tape, scores_[i].params);
                strat.prepare(sub_bar.bars.data(), sub_bar.bars.size());

                Account acct;
                SimulationParams sim;
                sim.initial_balance  = config_.initial_balance;
                sim.max_leverage     = config_.max_leverage;
                sim.risk_per_trade   = scores_[i].params.base_risk_fraction;
                sim.stop_out_level   = 50.0;
                sim.commission_per_lot = config_.commission;
                sim.slippage_points  = config_.slippage;
                sim.max_positions    = 1;
                acct.init(0, sim);

                std::vector<ReplayEntry> entries = {{&acct, &strat, &sim}};
                run_replay_v3(sub_bar.bars.data(), sub_bar.bars.size(),
                              entries, RunMode::BENCHMARK, nullptr, config_.risk_config);

                double ret = (acct.state.equity - acct.state.initial_balance) / acct.state.initial_balance;
                scores_arr[w] = ret;
                any_valid = true;
            }

            if (any_valid) {
                double mean = (scores_arr[0] + scores_arr[1] + scores_arr[2]) / 3.0;
                double in_sample = scores_[i].total_return;
                double degradation = (in_sample > 0) ? (in_sample - mean) / in_sample : 0;
                scores_[i].robustness_score = std::max(0.0, 1.0 - std::max(0.0, degradation));
                scores_[i].composite_score  = compute_composite(scores_[i]);
            }
        }
    }

    // Extract finalists
    std::sort(scores_.begin(), scores_.end(),
        [](const auto& a, const auto& b) {
            return a.composite_score > b.composite_score;
        });

    for (const auto& s : scores_) {
        if (s.passes_threshold && !s.liquidated) {
            finalists_.push_back(s);
            if (finalists_.size() >= static_cast<size_t>(config_.elite_count * 2))
                break;
        }
    }

    write_finalist_report();

    auto t_end = std::chrono::high_resolution_clock::now();
    double total_secs = std::chrono::duration<double>(t_end - t_start).count();

    std::cout << "\n================================================================" << std::endl;
    std::cout << " HYDRA EVOLUTION COMPLETE" << std::endl;
    std::cout << " Total time: " << std::fixed << std::setprecision(1) << total_secs << "s" << std::endl;
    std::cout << " Finalists: " << finalists_.size() << std::endl;
    if (!finalists_.empty()) {
        std::cout << " Best composite: " << std::setprecision(3) << finalists_[0].composite_score << std::endl;
        std::cout << " Best monthly: "   << std::setprecision(1) << (finalists_[0].monthly_return * 100) << "%" << std::endl;
        std::cout << " Best drawdown: "  << (finalists_[0].max_drawdown * 100) << "%" << std::endl;
        std::cout << " Best trades: "    << finalists_[0].trade_count << std::endl;
        std::cout << " Best params: "    << finalists_[0].params.describe() << std::endl;
    }
    std::cout << "================================================================" << std::endl;
}


// ════════════════════════════════════════════════════════════
//  POPULATION MANAGEMENT
// ════════════════════════════════════════════════════════════

void HydraEvolutionEngine::initialize_population() {
    std::cout << "[hydra_evo] Initializing population of " << config_.population_size << std::endl;
    population_.clear();
    population_.reserve(config_.population_size);
    for (int i = 0; i < config_.population_size; ++i) {
        population_.push_back(random_hydra_params(rng_, next_id_++));
    }
}

void HydraEvolutionEngine::select_and_reproduce() {
    // Sort by composite score descending
    std::vector<size_t> indices(scores_.size());
    std::iota(indices.begin(), indices.end(), 0);
    std::sort(indices.begin(), indices.end(),
        [this](size_t a, size_t b) {
            return scores_[a].composite_score > scores_[b].composite_score;
        });

    std::vector<HydraExecutionParams> next_gen;
    next_gen.reserve(config_.population_size);

    // Elitism: carry top-k unchanged
    int elite = std::min(config_.elite_count, static_cast<int>(indices.size()));
    for (int i = 0; i < elite; ++i) {
        auto p = scores_[indices[i]].params;
        p.param_id = next_id_++;
        p.generation++;
        next_gen.push_back(std::move(p));
    }

    // Tournament selection + reproduction
    std::uniform_int_distribution<int> pop_dist(0, static_cast<int>(scores_.size()) - 1);
    std::uniform_real_distribution<float> coin(0.0f, 1.0f);

    auto tournament_select = [&]() -> size_t {
        size_t best = static_cast<size_t>(pop_dist(rng_));
        for (int j = 1; j < config_.tournament_k; ++j) {
            size_t challenger = static_cast<size_t>(pop_dist(rng_));
            if (scores_[challenger].composite_score > scores_[best].composite_score)
                best = challenger;
        }
        return best;
    };

    while (static_cast<int>(next_gen.size()) < config_.population_size) {
        size_t p1_idx = tournament_select();
        const auto& parent1 = scores_[p1_idx].params;

        HydraExecutionParams child;
        if (coin(rng_) < config_.crossover_rate) {
            size_t p2_idx = tournament_select();
            child = crossover_hydra_params(parent1, scores_[p2_idx].params, rng_);
        } else {
            child = parent1;
        }

        child = mutate_hydra_params(child, rng_, config_.mutation_rate);
        child.param_id = next_id_++;
        child.generation = parent1.generation + 1;
        next_gen.push_back(std::move(child));
    }

    population_ = std::move(next_gen);
}


// ════════════════════════════════════════════════════════════
//  EVALUATION
// ════════════════════════════════════════════════════════════

void HydraEvolutionEngine::evaluate_population() {
    // Always clear scores before evaluating the current population.
    scores_.clear();
    scores_.reserve(population_.size());

    const Bar*  bars     = bar_tape_.bars.data();
    size_t      num_bars = bar_tape_.bars.size();

    // Batch evaluate all candidates in one replay pass per batch.
    // We use batches of 50 so that memory stays bounded.
    constexpr size_t BATCH = 50;

    for (size_t start = 0; start < population_.size(); start += BATCH) {
        size_t end = std::min(start + BATCH, population_.size());
        size_t n   = end - start;

        std::vector<std::unique_ptr<HydraStrategy>> strategies;
        std::vector<Account>          accounts(n);
        std::vector<SimulationParams> sim_params(n);
        std::vector<ReplayEntry>      entries;

        strategies.reserve(n);
        entries.reserve(n);

        for (size_t i = 0; i < n; ++i) {
            const HydraExecutionParams& p = population_[start + i];

            strategies.push_back(std::make_unique<HydraStrategy>(signal_tape_, p));
            strategies.back()->prepare(bars, num_bars);

            sim_params[i].initial_balance    = config_.initial_balance;
            sim_params[i].max_leverage       = config_.max_leverage;
            sim_params[i].risk_per_trade     = p.base_risk_fraction;
            sim_params[i].stop_out_level     = 50.0;
            sim_params[i].commission_per_lot = config_.commission;
            sim_params[i].slippage_points    = config_.slippage;
            sim_params[i].max_positions      = 1;
            sim_params[i].live_safe_mode     = 0;

            accounts[i].init(static_cast<uint32_t>(start + i), sim_params[i]);

            // Log signal counts for first candidate of first batch to aid debug
            if (i == 0 && start == 0) {
                size_t long_cnt = 0, short_cnt = 0;
                for (size_t bi = 0; bi < num_bars; ++bi) {
                    Signal sig = strategies.back()->signal_at(bi);
                    if (sig == Signal::BULLISH_CROSS) long_cnt++;
                    else if (sig == Signal::BEARISH_CROSS) short_cnt++;
                }
                std::cerr << "[hydra_evo] first_candidate param_id=" << p.param_id
                          << " long=" << long_cnt << " short=" << short_cnt
                          << " total=" << (long_cnt + short_cnt)
                          << (long_cnt + short_cnt == 0 ? " [WARNING: zero signals]" : "")
                          << std::endl;
            }

            entries.push_back({&accounts[i], strategies[i].get(), &sim_params[i]});
        }

        run_replay_v3(bars, num_bars, entries, RunMode::BENCHMARK,
                      nullptr, config_.risk_config);

        // Extract metrics
        double bars_per_month = (bar_tape_.timeframe_seconds > 0)
            ? (30.0 * 24.0 * 3600.0) / bar_tape_.timeframe_seconds
            : 720.0;
        double months = static_cast<double>(num_bars) / bars_per_month;

        for (size_t i = 0; i < n; ++i) {
            HydraEvolutionScore s;
            s.params         = population_[start + i];
            s.param_id       = s.params.param_id;
            const auto& acct = accounts[i].state;

            s.liquidated     = (acct.liquidated != 0);
            s.total_return   = (acct.equity - acct.initial_balance) / acct.initial_balance;
            s.max_drawdown   = acct.max_drawdown;
            s.trade_count    = acct.total_trades;
            s.win_rate       = (acct.total_trades > 0)
                ? static_cast<double>(acct.winning_trades) / acct.total_trades : 0.0;
            s.profit_factor  = (acct.gross_loss < -1e-9)
                ? acct.gross_profit / std::fabs(acct.gross_loss) : 0.0;

            if (months > 0 && s.total_return > -1.0 && !s.liquidated) {
                s.monthly_return = std::pow(1.0 + s.total_return, 1.0 / months) - 1.0;
            } else {
                s.monthly_return = -1.0;
            }

            // Consistency from equity curve
            s.consistency = 0.0;
            if (!accounts[i].equity_curve.empty() && accounts[i].equity_curve.size() > 10) {
                const auto& ec = accounts[i].equity_curve;
                size_t seg = ec.size() / 10;
                int pos = 0;
                for (int w = 0; w < 10; ++w) {
                    size_t si = w * seg;
                    size_t ei = std::min(si + seg, ec.size()) - 1;
                    if (ec[ei] > ec[si]) pos++;
                }
                s.consistency = static_cast<double>(pos) / 10.0;
            }

            s.composite_score = compute_composite(s);
            scores_.push_back(std::move(s));
        }
    }
}

HydraEvolutionScore HydraEvolutionEngine::evaluate_candidate(
    const HydraExecutionParams& params
) {
    std::vector<HydraExecutionParams> batch = {params};
    // Temporarily push to population, evaluate one, restore
    size_t saved = population_.size();
    population_.push_back(params);

    HydraEvolutionScore result;
    const Bar*  bars     = bar_tape_.bars.data();
    size_t      num_bars = bar_tape_.bars.size();

    HydraStrategy strat(signal_tape_, params);
    strat.prepare(bars, num_bars);

    Account acct;
    SimulationParams sim;
    sim.initial_balance    = config_.initial_balance;
    sim.max_leverage       = config_.max_leverage;
    sim.risk_per_trade     = params.base_risk_fraction;
    sim.stop_out_level     = 50.0;
    sim.commission_per_lot = config_.commission;
    sim.slippage_points    = config_.slippage;
    sim.max_positions      = 1;
    acct.init(0, sim);

    std::vector<ReplayEntry> entries = {{&acct, &strat, &sim}};
    run_replay_v3(bars, num_bars, entries, RunMode::BENCHMARK,
                  nullptr, config_.risk_config);

    result.params      = params;
    result.param_id    = params.param_id;
    result.liquidated  = (acct.state.liquidated != 0);
    result.total_return = (acct.state.equity - acct.state.initial_balance)
                         / acct.state.initial_balance;
    result.max_drawdown  = acct.state.max_drawdown;
    result.trade_count   = acct.state.total_trades;
    result.win_rate      = (acct.state.total_trades > 0)
        ? static_cast<double>(acct.state.winning_trades) / acct.state.total_trades : 0.0;
    result.profit_factor = (acct.state.gross_loss < -1e-9)
        ? acct.state.gross_profit / std::fabs(acct.state.gross_loss) : 0.0;

    double bars_per_month = (bar_tape_.timeframe_seconds > 0)
        ? (30.0 * 24.0 * 3600.0) / bar_tape_.timeframe_seconds : 720.0;
    double months = static_cast<double>(num_bars) / bars_per_month;
    if (months > 0 && result.total_return > -1.0 && !result.liquidated)
        result.monthly_return = std::pow(1.0 + result.total_return, 1.0 / months) - 1.0;
    else
        result.monthly_return = -1.0;

    result.composite_score = compute_composite(result);

    // Restore population
    population_.resize(saved);
    return result;
}


// ════════════════════════════════════════════════════════════
//  COMPOSITE SCORING
// ════════════════════════════════════════════════════════════

double HydraEvolutionEngine::compute_composite(const HydraEvolutionScore& s) const {
    if (s.liquidated) return -1e6;
    if (s.trade_count < 5) return -1e5;

    double min_ret = std::max(config_.min_monthly_return, 0.01);

    // Normalized return (0..2)
    double monthly_return_norm = std::min(2.0,
        std::max(0.0, s.monthly_return / min_ret));

    // Risk-adjusted return (0..5)
    double risk_adjusted_return = std::min(5.0,
        s.monthly_return / std::max(s.max_drawdown, 0.001));

    // Profit factor normalized (0..3)
    double profit_factor_norm = std::min(3.0,
        std::max(0.0, s.profit_factor - 1.0));

    double consistency   = std::max(0.0, s.consistency);
    double robustness    = std::max(0.0, s.robustness_score);

    double composite = monthly_return_norm   * 0.30
                     + risk_adjusted_return  * 0.20
                     + profit_factor_norm    * 0.20
                     + consistency          * 0.15
                     + robustness           * 0.15;

    // Bonus if ALL thresholds met simultaneously
    if (s.monthly_return >= config_.min_monthly_return &&
        s.max_drawdown   <= config_.max_drawdown_limit &&
        s.profit_factor  >= config_.min_profit_factor  &&
        s.trade_count    >= config_.min_trade_count) {
        composite += 0.5;
    }

    // Overtrading penalty: >200 trades/month on H1 is likely overfit
    double bars_per_month = (bar_tape_.timeframe_seconds > 0)
        ? (30.0 * 24.0 * 3600.0) / bar_tape_.timeframe_seconds : 720.0;
    double num_bars = static_cast<double>(bar_tape_.bars.size());
    double months   = (bars_per_month > 0) ? num_bars / bars_per_month : 1.0;
    double trades_per_month = (months > 0)
        ? static_cast<double>(s.trade_count) / months : 0.0;
    if (trades_per_month > 200.0) {
        composite -= (trades_per_month - 200.0) / 200.0 * 0.1;
    }

    return composite;
}


// ════════════════════════════════════════════════════════════
//  REPORTING
// ════════════════════════════════════════════════════════════

void HydraEvolutionEngine::write_generation_summary(int gen) const {
    if (!config_.checkpoint_enabled) return;

    auto path = config_.output_dir / ("hydra_gen_" + std::to_string(gen) + "_summary.txt");
    std::ofstream out(path);
    if (!out) return;

    std::vector<size_t> idx(scores_.size());
    std::iota(idx.begin(), idx.end(), 0);
    std::sort(idx.begin(), idx.end(),
        [this](size_t a, size_t b) {
            return scores_[a].composite_score > scores_[b].composite_score;
        });

    out << "Hydra Generation " << gen << " — " << scores_.size() << " candidates\n";
    out << std::string(80, '=') << "\n\n";

    int passing = 0;
    for (const auto& s : scores_) if (s.passes_threshold) passing++;
    out << "Passing threshold: " << passing << "\n\n";

    out << "Top 20:\n";
    out << std::setw(6) << "Rank" << " "
        << std::setw(10) << "ID" << " "
        << std::setw(10) << "MonthRet" << " "
        << std::setw(10) << "MaxDD" << " "
        << std::setw(8)  << "PF"   << " "
        << std::setw(8)  << "Trades" << " "
        << std::setw(8)  << "WinRate" << " "
        << std::setw(10) << "Composite" << " "
        << std::setw(6)  << "Pass" << "\n";
    out << std::string(90, '-') << "\n";

    int show = std::min(20, static_cast<int>(idx.size()));
    for (int i = 0; i < show; ++i) {
        const auto& s = scores_[idx[i]];
        out << std::setw(6)  << (i + 1) << " "
            << std::setw(10) << s.param_id << " "
            << std::setw(9)  << std::fixed << std::setprecision(1) << (s.monthly_return * 100) << "% "
            << std::setw(9)  << (s.max_drawdown * 100) << "% "
            << std::setw(8)  << std::setprecision(2) << s.profit_factor << " "
            << std::setw(8)  << s.trade_count << " "
            << std::setw(7)  << std::setprecision(1) << (s.win_rate * 100) << "% "
            << std::setw(10) << std::setprecision(3) << s.composite_score << " "
            << std::setw(6)  << (s.passes_threshold ? "YES" : "no") << "\n";
    }
    out << "\n";
    if (!idx.empty()) {
        out << "Best params: " << scores_[idx[0]].params.describe() << "\n";
    }
}

void HydraEvolutionEngine::write_finalist_report() const {
    if (finalists_.empty()) return;

    // Plain text report
    auto txt_path = config_.output_dir / "hydra_finalists.txt";
    std::ofstream txt(txt_path);
    if (txt) {
        txt << "HYDRA EVOLUTION FINALISTS\n";
        txt << std::string(70, '=') << "\n\n";
        txt << "Total: " << finalists_.size() << "\n\n";
        for (size_t i = 0; i < finalists_.size(); ++i) {
            const auto& f = finalists_[i];
            txt << "--- Finalist #" << (i + 1) << " ---\n";
            txt << "  Params: "      << f.params.describe() << "\n";
            txt << "  Monthly: "     << (f.monthly_return * 100) << "%\n";
            txt << "  Total return: "<< (f.total_return * 100) << "%\n";
            txt << "  Max drawdown: "<< (f.max_drawdown * 100) << "%\n";
            txt << "  Profit factor: "<< f.profit_factor << "\n";
            txt << "  Win rate: "    << (f.win_rate * 100) << "%\n";
            txt << "  Trades: "      << f.trade_count << "\n";
            txt << "  Consistency: " << f.consistency << "\n";
            txt << "  Composite: "   << f.composite_score << "\n";
            if (f.robustness_score > 0)
                txt << "  Robustness: " << f.robustness_score << "\n";
            txt << "\n";
        }
    }

    // JSON for machine consumption
    auto json_path = config_.output_dir / "finalists.json";
    std::ofstream json(json_path);
    if (!json) return;

    json << "[\n";
    for (size_t i = 0; i < finalists_.size(); ++i) {
        if (i > 0) json << ",\n";
        const auto& f = finalists_[i];
        json << "  {\n";
        json << "    \"param_id\": "       << f.param_id       << ",\n";
        json << "    \"monthly_return\": " << f.monthly_return  << ",\n";
        json << "    \"total_return\": "   << f.total_return    << ",\n";
        json << "    \"max_drawdown\": "   << f.max_drawdown    << ",\n";
        json << "    \"profit_factor\": "  << f.profit_factor   << ",\n";
        json << "    \"win_rate\": "       << f.win_rate        << ",\n";
        json << "    \"trade_count\": "    << f.trade_count     << ",\n";
        json << "    \"consistency\": "    << f.consistency     << ",\n";
        json << "    \"composite_score\": "<< f.composite_score << ",\n";
        json << "    \"robustness_score\": "<< f.robustness_score << ",\n";
        json << "    \"params\": " << f.params.serialize_json() << "\n";
        json << "  }";
    }
    json << "\n]\n";

    std::cout << "[hydra_evo] Finalist report written to "
              << json_path.string() << std::endl;
}

} // namespace aphelion
