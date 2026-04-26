// ============================================================
// Aphelion Research — Main Entry Point
//
// CLI-driven harness for replay, tournament, evolution, and
// Hydra signal-tape driven execution parameter search.
//
// Usage:
//   aphelion --data-root <path> [options]
//
// Core modes:
//   (default)        Run tournament of SMA strategies
//   --evolve         Run GenomeStrategy evolution
//   --hydra-tape P   Load ML signal tape; use HydraStrategy
//   --hydra-evolve   Search HydraExecutionParams space (requires --hydra-tape)
// ============================================================

#include "aphelion/data_ingest.h"
#include "aphelion/tournament.h"
#include "aphelion/evolution_engine.h"
#include "aphelion/hydra_strategy.h"
#include "aphelion/hydra_evolution.h"
#include "aphelion/intelligence.h"
#include "aphelion/replay_engine.h"
#include "aphelion/account.h"
#include "aphelion/multi_timeframe.h"

#include <algorithm>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <iostream>
#include <string>
#include <vector>

namespace fs = std::filesystem;

using namespace aphelion;

// ── Minimal CLI parser ──────────────────────────────────────
struct Args {
    // Data
    std::string data_root;
    std::string symbol       = "XAUUSD";
    std::string timeframe    = "H1";
    std::vector<std::string> context_tfs;

    // Simulation basics
    int    accounts          = 100;
    double leverage          = 100.0;
    double risk              = 0.01;
    std::string mode_str     = "research";
    std::string output_dir   = "output";

    // Standard evolution
    bool   evolve            = false;
    int    pop_size          = 500;
    int    generations       = 100;
    int    elite_count       = 20;
    float  mutation_rate     = 0.15f;

    // Hydra signal tape
    std::string hydra_tape;

    // Hydra evolution
    bool   hydra_evolve      = false;
    double min_monthly_return = 0.05;
    double max_drawdown       = 0.20;
    double min_profit_factor  = 1.15;
    int    min_trade_count    = 15;
    int    evolution_seed     = 42;
    std::string evolution_output = "hydra_evolution_output";

    bool   help              = false;
};

static void print_help(const char* prog) {
    std::cout << "Usage: " << prog << " --data-root <path> [options]\n\n";
    std::cout << "Data options:\n";
    std::cout << "  --data-root <path>           Root dir containing Parquet bar data\n";
    std::cout << "  --symbol <str>               Symbol (default: XAUUSD)\n";
    std::cout << "  --timeframe <str>            Timeframe (default: H1)\n";
    std::cout << "  --context-tf <str>           Context timeframe (repeatable)\n\n";
    std::cout << "Simulation options:\n";
    std::cout << "  --accounts <int>             Accounts in tournament (default: 100)\n";
    std::cout << "  --leverage <float>           Max leverage (default: 100)\n";
    std::cout << "  --risk <float>               Risk per trade fraction (default: 0.01)\n";
    std::cout << "  --mode <str>                 Run mode: full|benchmark|research (default: research)\n";
    std::cout << "  --output <path>              Output directory (default: output)\n\n";
    std::cout << "Evolution options:\n";
    std::cout << "  --evolve                     Run GenomeStrategy evolution\n";
    std::cout << "  --pop-size <int>             Population size (default: 500)\n";
    std::cout << "  --generations <int>          Generations (default: 100)\n";
    std::cout << "  --elite-count <int>          Elite carry-over (default: 20)\n";
    std::cout << "  --mutation-rate <float>      Mutation rate (default: 0.15)\n";
    std::cout << "  --evolution-output <path>    Evolution output dir (default: hydra_evolution_output)\n";
    std::cout << "  --evolution-seed <int>       RNG seed (default: 42)\n\n";
    std::cout << "Hydra options:\n";
    std::cout << "  --hydra-tape <path>          Path to signal_tape_*.parquet from Python HYDRA\n";
    std::cout << "  --hydra-evolve               Search HydraExecutionParams (requires --hydra-tape)\n";
    std::cout << "  --min-monthly-return <float> Min monthly return threshold (default: 0.05)\n";
    std::cout << "  --max-drawdown <float>       Max drawdown limit (default: 0.20)\n";
    std::cout << "  --min-profit-factor <float>  Min profit factor (default: 1.15)\n\n";
    std::cout << "  --help                       Show this help\n";
}

static Args parse_args(int argc, char** argv) {
    Args args;
    for (int i = 1; i < argc; ++i) {
        std::string key = argv[i];
        auto next = [&]() -> std::string {
            if (i + 1 >= argc) {
                std::cerr << "ERROR: " << key << " requires an argument\n";
                std::exit(1);
            }
            return argv[++i];
        };

        if (key == "--data-root")           args.data_root   = next();
        else if (key == "--symbol")         args.symbol      = next();
        else if (key == "--timeframe")      args.timeframe   = next();
        else if (key == "--context-tf")     args.context_tfs.push_back(next());
        else if (key == "--accounts")       args.accounts    = std::stoi(next());
        else if (key == "--leverage")       args.leverage    = std::stod(next());
        else if (key == "--risk")           args.risk        = std::stod(next());
        else if (key == "--mode")           args.mode_str    = next();
        else if (key == "--output")         args.output_dir  = next();
        else if (key == "--evolve")         args.evolve      = true;
        else if (key == "--pop-size")       args.pop_size    = std::stoi(next());
        else if (key == "--generations")    args.generations = std::stoi(next());
        else if (key == "--elite-count")    args.elite_count = std::stoi(next());
        else if (key == "--mutation-rate")  args.mutation_rate = std::stof(next());
        else if (key == "--hydra-tape")     args.hydra_tape  = next();
        else if (key == "--hydra-evolve")   args.hydra_evolve = true;
        else if (key == "--min-monthly-return") args.min_monthly_return = std::stod(next());
        else if (key == "--max-drawdown")   args.max_drawdown = std::stod(next());
        else if (key == "--min-profit-factor") args.min_profit_factor = std::stod(next());
        else if (key == "--min-trade-count") args.min_trade_count = std::stoi(next());
        else if (key == "--evolution-seed") args.evolution_seed  = std::stoi(next());
        else if (key == "--evolution-output") args.evolution_output = next();
        else if (key == "--help" || key == "-h") args.help = true;
        else {
            std::cerr << "Unknown option: " << key << "\n";
            std::exit(1);
        }
    }
    return args;
}

static RunMode parse_mode(const std::string& s) {
    if (s == "benchmark") return RunMode::BENCHMARK;
    if (s == "full")      return RunMode::FULL;
    return RunMode::FULL;  // default
}


// ════════════════════════════════════════════════════════════
//  TOURNAMENT (default)
// ════════════════════════════════════════════════════════════

static void run_tournament(const Args& args, const BarTape& tape) {
    TournamentConfig cfg;
    cfg.num_accounts    = args.accounts;
    cfg.initial_balance = 10000.0;
    cfg.max_leverage    = args.leverage;
    cfg.risk_per_trade  = args.risk;
    cfg.mode            = parse_mode(args.mode_str);

    Tournament tournament(cfg, tape);
    tournament.initialize();

    auto t0 = std::chrono::high_resolution_clock::now();
    tournament.run();
    auto t1 = std::chrono::high_resolution_clock::now();
    double secs = std::chrono::duration<double>(t1 - t0).count();

    auto lb = tournament.leaderboard();
    std::cout << "\nTournament complete in " << secs << "s\n";
    std::cout << "Top 10 results:\n";
    int show = std::min(10, static_cast<int>(lb.size()));
    for (int i = 0; i < show; ++i) {
        const auto& r = lb[i];
        std::cout << "  #" << (i+1) << " return=" << (r.total_return * 100)
                  << "% dd=" << (r.max_drawdown * 100)
                  << "% pf=" << r.profit_factor
                  << " trades=" << r.trade_count
                  << " (" << r.strategy_name << ")\n";
    }
}


// ════════════════════════════════════════════════════════════
//  TOURNAMENT WITH HYDRA STRATEGY
// ════════════════════════════════════════════════════════════

static void run_hydra_tournament(
    const Args& args,
    const BarTape& tape,
    const HydraSignalTape& signal_tape
) {
    std::cout << "[hydra] Running tournament with default HydraExecutionParams\n";
    std::cout << "[hydra] Signal bars: " << signal_tape.size() << "\n";
    std::cout << "[hydra] Bar bars:    " << tape.bars.size() << "\n";

    HydraExecutionParams params;  // use defaults
    HydraStrategy strat(signal_tape, params);
    strat.prepare(tape.bars.data(), tape.bars.size());

    // Log signal count
    size_t long_cnt = 0, short_cnt = 0;
    for (size_t i = 0; i < tape.bars.size(); ++i) {
        Signal s = strat.signal_at(i);
        if (s == Signal::BULLISH_CROSS) long_cnt++;
        else if (s == Signal::BEARISH_CROSS) short_cnt++;
    }
    std::cout << "[hydra] Signals: long=" << long_cnt
              << " short=" << short_cnt
              << " total=" << (long_cnt + short_cnt) << "\n";

    SimulationParams sim;
    sim.initial_balance    = 10000.0;
    sim.max_leverage       = args.leverage;
    sim.risk_per_trade     = args.risk;
    sim.stop_out_level     = 50.0;
    sim.max_positions      = 1;

    Account acct;
    acct.init(0, sim);

    std::vector<ReplayEntry> entries = {{&acct, &strat, &sim}};

    auto t0 = std::chrono::high_resolution_clock::now();
    auto stats = run_replay_v3(tape.bars.data(), tape.bars.size(),
                               entries, parse_mode(args.mode_str),
                               nullptr, RiskConfig{});
    auto t1 = std::chrono::high_resolution_clock::now();
    double secs = std::chrono::duration<double>(t1 - t0).count();

    std::cout << "\nHydra single-param replay complete in " << secs << "s\n";
    std::cout << "  Bars/sec:      " << stats.bars_processed / std::max(secs, 1e-9) << "\n";
    std::cout << "  Fills:         " << stats.total_fills << "\n";
    std::cout << "  Return:        "
              << ((acct.state.equity - acct.state.initial_balance) / acct.state.initial_balance * 100)
              << "%\n";
    std::cout << "  Max drawdown:  " << (acct.state.max_drawdown * 100) << "%\n";
    std::cout << "  Trades:        " << acct.state.total_trades << "\n";
    if (acct.state.gross_loss < -1e-9)
        std::cout << "  Profit factor: "
                  << (acct.state.gross_profit / std::fabs(acct.state.gross_loss)) << "\n";
}


// ════════════════════════════════════════════════════════════
//  GENOME EVOLUTION
// ════════════════════════════════════════════════════════════

static void run_genome_evolution(const Args& args, const BarTape& tape) {
    EvolutionConfig cfg;
    cfg.population_size     = args.pop_size;
    cfg.generations         = args.generations;
    cfg.elite_count         = args.elite_count;
    cfg.mutation_rate       = args.mutation_rate;
    cfg.min_monthly_return  = args.min_monthly_return;
    cfg.max_drawdown_limit  = args.max_drawdown;
    cfg.min_profit_factor   = args.min_profit_factor;
    cfg.min_trade_count     = args.min_trade_count;
    cfg.random_seed         = static_cast<uint64_t>(args.evolution_seed);
    cfg.output_dir          = args.evolution_output;
    cfg.initial_balance     = 10000.0;
    cfg.max_leverage        = args.leverage;
    cfg.checkpoint_enabled  = true;

    std::vector<MultiTimeframeInput> context_inputs;
    for (const auto& tf : args.context_tfs) {
        auto ctx_tape = load_bar_tape(args.data_root, args.symbol, tf);
        MultiTimeframeInput input;
        input.tape = std::move(ctx_tape);
        context_inputs.push_back(std::move(input));
    }

    EvolutionEngine engine(cfg, tape, context_inputs);
    engine.run();

    const auto& finalists = engine.finalists();
    std::cout << "\nGenome evolution complete. Finalists: " << finalists.size() << "\n";
}


// ════════════════════════════════════════════════════════════
//  HYDRA EVOLUTION
// ════════════════════════════════════════════════════════════

static void run_hydra_evolution(
    const Args& args,
    const BarTape& tape,
    const HydraSignalTape& signal_tape
) {
    HydraEvolutionConfig cfg;
    cfg.population_size     = args.pop_size;
    cfg.generations         = args.generations;
    cfg.elite_count         = args.elite_count;
    cfg.mutation_rate       = args.mutation_rate;
    cfg.min_monthly_return  = args.min_monthly_return;
    cfg.max_drawdown_limit  = args.max_drawdown;
    cfg.min_profit_factor   = args.min_profit_factor;
    cfg.min_trade_count     = args.min_trade_count;
    cfg.random_seed         = static_cast<uint64_t>(args.evolution_seed);
    cfg.output_dir          = args.evolution_output;
    cfg.initial_balance     = 10000.0;
    cfg.max_leverage        = args.leverage;
    cfg.checkpoint_enabled  = true;

    HydraEvolutionEngine engine(cfg, tape, signal_tape);
    engine.run();

    const auto& finalists = engine.finalists();
    std::cout << "\nHydra evolution complete. Finalists: " << finalists.size() << "\n";

    if (!finalists.empty()) {
        const auto& best = finalists[0];
        std::cout << "\nBest execution params:\n";
        std::cout << "  " << best.params.describe() << "\n";
        std::cout << "  Monthly return: " << (best.monthly_return * 100) << "%\n";
        std::cout << "  Max drawdown:   " << (best.max_drawdown * 100) << "%\n";
        std::cout << "  Profit factor:  " << best.profit_factor << "\n";
        std::cout << "  Trades:         " << best.trade_count << "\n";
    }
}


// ════════════════════════════════════════════════════════════
//  MAIN
// ════════════════════════════════════════════════════════════

int main(int argc, char** argv) {
    Args args = parse_args(argc, argv);

    if (args.help || args.data_root.empty()) {
        print_help(argv[0]);
        return args.data_root.empty() && !args.help ? 1 : 0;
    }

    if (args.hydra_evolve && args.hydra_tape.empty()) {
        std::cerr << "ERROR: --hydra-evolve requires --hydra-tape <path>\n";
        return 1;
    }

    // ── Load primary bar tape ───────────────────────────────
    std::cout << "[main] Loading bars: " << args.symbol << " " << args.timeframe
              << " from " << args.data_root << std::endl;
    BarTape tape = load_bar_tape(args.data_root, args.symbol, args.timeframe);
    std::cout << "[main] Loaded " << tape.bars.size() << " bars ("
              << tape.timeframe_seconds << "s timeframe)\n";

    if (tape.bars.empty()) {
        std::cerr << "ERROR: No bars loaded — check data-root and symbol/timeframe\n";
        return 1;
    }

    // ── Hydra signal tape (if provided) ─────────────────────
    HydraSignalTape signal_tape;
    bool has_hydra_tape = !args.hydra_tape.empty();
    if (has_hydra_tape) {
        std::cout << "[main] Loading Hydra signal tape: " << args.hydra_tape << std::endl;
        signal_tape = load_hydra_signal_tape(fs::path(args.hydra_tape), tape);
        std::cout << "[main] Signal tape loaded: " << signal_tape.size() << " entries\n";
    }

    // ── Dispatch ─────────────────────────────────────────────
    if (has_hydra_tape && args.hydra_evolve) {
        run_hydra_evolution(args, tape, signal_tape);
    } else if (has_hydra_tape) {
        run_hydra_tournament(args, tape, signal_tape);
    } else if (args.evolve) {
        run_genome_evolution(args, tape);
    } else {
        run_tournament(args, tape);
    }

    return 0;
}
