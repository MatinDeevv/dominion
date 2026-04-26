#pragma once
// ============================================================
// Aphelion Research — Hydra Evolution Engine
//
// Evolutionary search over HydraExecutionParams space.
// Uses the C++ replay infrastructure to evaluate each candidate
// with a HydraStrategy driven by an ML signal tape, then applies
// tournament selection, crossover, and mutation to find the
// optimal execution parameters around those signals.
// ============================================================

#include "aphelion/hydra_strategy.h"
#include "aphelion/data_ingest.h"
#include "aphelion/robustness_validator.h"
#include "aphelion/risk_manager.h"

#include <filesystem>
#include <random>
#include <vector>
#include <string>

namespace aphelion {

// ── Hydra evolution configuration ──────────────────────────
struct HydraEvolutionConfig {
    // Population
    int      population_size    = 200;
    int      generations        = 50;
    int      elite_count        = 10;

    // Genetic operators
    float    mutation_rate      = 0.20f;
    float    crossover_rate     = 0.65f;
    int      tournament_k       = 5;

    // Acceptance thresholds (realistic for XAU/USD H1)
    double   min_monthly_return = 0.05;   // 5%
    double   max_drawdown_limit = 0.20;   // 20%
    double   min_profit_factor  = 1.15;
    int      min_trade_count    = 15;

    // Robustness
    int      robustness_top_k   = 20;
    bool     enable_robustness  = true;
    RobustnessConfig robustness_config;

    // Simulation
    double   initial_balance    = 10000.0;
    double   max_leverage       = 100.0;
    double   risk_per_trade     = 0.01;
    double   commission         = 0.0;
    double   slippage           = 0.0;
    RiskConfig risk_config;

    // Output / checkpointing
    uint64_t random_seed        = 42;
    std::filesystem::path output_dir = "hydra_evolution_output";
    bool     checkpoint_enabled = true;
    int      checkpoint_interval = 5;
    bool     verbose            = false;
};

// ── Per-candidate score ────────────────────────────────────
struct HydraEvolutionScore {
    uint64_t              param_id         = 0;
    double                total_return     = 0.0;
    double                monthly_return   = 0.0;
    double                max_drawdown     = 0.0;
    double                profit_factor    = 0.0;
    double                win_rate         = 0.0;
    int                   trade_count      = 0;
    double                consistency      = 0.0;
    double                composite_score  = 0.0;
    double                robustness_score = 0.0;
    bool                  passes_threshold = false;
    bool                  liquidated       = false;
    HydraExecutionParams  params;
    RobustnessResult      robustness;
};

// ── Hydra Evolution Engine ─────────────────────────────────
class HydraEvolutionEngine {
public:
    HydraEvolutionEngine(
        const HydraEvolutionConfig& config,
        const BarTape& bar_tape,
        const HydraSignalTape& signal_tape
    );

    void run();

    const std::vector<HydraEvolutionScore>& finalists() const { return finalists_; }
    void write_finalist_report() const;

private:
    HydraEvolutionConfig                   config_;
    const BarTape&                         bar_tape_;
    const HydraSignalTape&                 signal_tape_;

    std::vector<HydraExecutionParams>      population_;
    std::vector<HydraEvolutionScore>       scores_;
    std::vector<HydraEvolutionScore>       finalists_;
    std::mt19937                           rng_;
    uint64_t                               next_id_ = 1;

    void initialize_population();
    void evaluate_population();
    HydraEvolutionScore evaluate_candidate(const HydraExecutionParams& params);
    double compute_composite(const HydraEvolutionScore& s) const;
    void select_and_reproduce();
    void write_generation_summary(int gen) const;
};

} // namespace aphelion
