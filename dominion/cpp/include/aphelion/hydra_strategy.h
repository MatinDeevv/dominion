#pragma once
// ============================================================
// DOMINION HYDRA strategy adapter
//
// Consumes a per-bar ML signal tape exported from Python and turns it
// into zero-allocation replay decisions for the C++ engine.
// ============================================================

#include "aphelion/data_ingest.h"
#include "aphelion/strategy.h"

#include <cstdint>
#include <filesystem>
#include <random>
#include <string>
#include <vector>

namespace aphelion {

struct HydraSignal {
    int8_t direction = 0;    // 0=NONE, 1=LONG, 2=SHORT
    float confidence = 0.0f;
    int8_t regime = 0;
};

struct HydraSignalTape {
    std::vector<HydraSignal> signals;

    size_t size() const { return signals.size(); }
    const HydraSignal& at(size_t i) const { return signals[i]; }
};

HydraSignalTape load_hydra_signal_tape(
    const std::filesystem::path& path,
    const BarTape& bar_tape
);

struct HydraExecutionParams {
    float confidence_threshold = 0.50f;
    float confidence_high = 0.75f;
    float confidence_extreme = 0.90f;

    uint8_t allowed_regimes = 0b00000110;

    float sl_atr_multiple = 1.5f;
    float tp_atr_multiple = 2.5f;
    int16_t max_hold_bars = 30;
    int16_t min_hold_bars = 3;

    float base_risk_fraction = 0.01f;
    float high_conf_risk_scale = 1.25f;
    float extreme_conf_risk_scale = 1.50f;

    int16_t cooldown_bars = 5;

    uint64_t param_id = 0;
    uint64_t parent_id1 = 0;
    uint64_t parent_id2 = 0;
    uint32_t generation = 0;
    uint32_t mutation_count = 0;

    std::string describe() const;
    std::string serialize_json() const;
    static HydraExecutionParams deserialize_json(const std::string& json);
    int complexity() const;
};

HydraExecutionParams random_hydra_params(std::mt19937& rng, uint64_t id);
HydraExecutionParams mutate_hydra_params(
    const HydraExecutionParams& p,
    std::mt19937& rng,
    float rate
);
HydraExecutionParams crossover_hydra_params(
    const HydraExecutionParams& p1,
    const HydraExecutionParams& p2,
    std::mt19937& rng
);

class HydraStrategy : public IStrategy {
public:
    HydraStrategy(
        const HydraSignalTape& signal_tape,
        const HydraExecutionParams& params
    );

    StrategyDecision decide(
        const MarketState& market,
        const AccountState& account,
        size_t bar_index
    ) override;

    StrategyDecision decide_with_intelligence(
        const MarketState& market,
        const AccountState& account,
        size_t bar_index,
        const IntelligenceState& intelligence
    ) override;

    const char* name() const override { return "HydraML"; }
    void prepare(const Bar* tape, size_t tape_size) override;

    bool has_signal_tape() const override { return !precomputed_signal_.empty(); }
    Signal signal_at(size_t bar_idx) const override;
    size_t min_signal_bar() const override { return 0; }
    bool is_intelligence_aware() const override { return true; }

private:
    const HydraSignalTape& signal_tape_;
    HydraExecutionParams params_;
    std::vector<float> atr_tape_;
    std::vector<uint8_t> precomputed_signal_;
    int16_t bars_since_last_exit_ = 0;

    void compile_signal_tape(const Bar* bars, size_t n);
    StrategyDecision build_decision(
        const HydraSignal& sig,
        double close,
        double atr,
        int open_positions
    ) const;
};

} // namespace aphelion
