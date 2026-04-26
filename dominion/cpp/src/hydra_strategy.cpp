#include "aphelion/hydra_strategy.h"

#include <arrow/api.h>
#include <arrow/io/file.h>
#include <parquet/arrow/reader.h>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <cmath>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <unordered_map>

namespace aphelion {

namespace {

constexpr int8_t HYDRA_NONE = 0;
constexpr int8_t HYDRA_LONG = 1;
constexpr int8_t HYDRA_SHORT = 2;

void check_arrow(const arrow::Status& status, const char* context) {
    if (!status.ok()) {
        throw std::runtime_error(std::string(context) + ": " + status.ToString());
    }
}

std::shared_ptr<arrow::Table> read_parquet_table(const std::filesystem::path& path) {
    auto infile = arrow::io::ReadableFile::Open(path.string());
    if (!infile.ok()) {
        throw std::runtime_error("Cannot open signal tape " + path.string() + ": " + infile.status().ToString());
    }

    auto reader_result = parquet::arrow::OpenFile(*infile, arrow::default_memory_pool());
    if (!reader_result.ok()) {
        throw std::runtime_error("Parquet OpenFile: " + reader_result.status().ToString());
    }

    std::shared_ptr<arrow::Table> table;
    check_arrow((*reader_result)->ReadTable(&table), "ReadTable");
    return table;
}

std::shared_ptr<arrow::ChunkedArray> require_column(
    const std::shared_ptr<arrow::Table>& table,
    const std::string& name
) {
    auto column = table->GetColumnByName(name);
    if (!column) {
        throw std::runtime_error("Signal tape column not found: " + name);
    }
    return column;
}

std::vector<int64_t> extract_time_ms(const std::shared_ptr<arrow::Table>& table) {
    auto column = require_column(table, "time_ms");
    std::vector<int64_t> out;
    out.reserve(static_cast<size_t>(table->num_rows()));
    for (int c = 0; c < column->num_chunks(); ++c) {
        auto chunk = column->chunk(c);
        if (auto arr = std::dynamic_pointer_cast<arrow::Int64Array>(chunk)) {
            for (int64_t i = 0; i < arr->length(); ++i) out.push_back(arr->Value(i));
        } else if (auto ts = std::dynamic_pointer_cast<arrow::TimestampArray>(chunk)) {
            auto ts_type = std::static_pointer_cast<arrow::TimestampType>(ts->type());
            for (int64_t i = 0; i < ts->length(); ++i) {
                int64_t value = ts->Value(i);
                switch (ts_type->unit()) {
                    case arrow::TimeUnit::SECOND: value *= 1000; break;
                    case arrow::TimeUnit::MILLI: break;
                    case arrow::TimeUnit::MICRO: value /= 1000; break;
                    case arrow::TimeUnit::NANO: value /= 1000000; break;
                }
                out.push_back(value);
            }
        } else {
            throw std::runtime_error("Unsupported time_ms column type: " + chunk->type()->ToString());
        }
    }
    return out;
}

std::vector<int8_t> extract_i8(const std::shared_ptr<arrow::Table>& table, const std::string& name) {
    auto column = require_column(table, name);
    std::vector<int8_t> out;
    out.reserve(static_cast<size_t>(table->num_rows()));
    for (int c = 0; c < column->num_chunks(); ++c) {
        auto chunk = column->chunk(c);
        if (auto arr = std::dynamic_pointer_cast<arrow::Int8Array>(chunk)) {
            for (int64_t i = 0; i < arr->length(); ++i) out.push_back(arr->Value(i));
        } else if (auto arr = std::dynamic_pointer_cast<arrow::UInt8Array>(chunk)) {
            for (int64_t i = 0; i < arr->length(); ++i) out.push_back(static_cast<int8_t>(arr->Value(i)));
        } else if (auto arr = std::dynamic_pointer_cast<arrow::Int16Array>(chunk)) {
            for (int64_t i = 0; i < arr->length(); ++i) out.push_back(static_cast<int8_t>(arr->Value(i)));
        } else if (auto arr = std::dynamic_pointer_cast<arrow::Int32Array>(chunk)) {
            for (int64_t i = 0; i < arr->length(); ++i) out.push_back(static_cast<int8_t>(arr->Value(i)));
        } else {
            throw std::runtime_error("Unsupported " + name + " column type: " + chunk->type()->ToString());
        }
    }
    return out;
}

std::vector<float> extract_f32(const std::shared_ptr<arrow::Table>& table, const std::string& name) {
    auto column = require_column(table, name);
    std::vector<float> out;
    out.reserve(static_cast<size_t>(table->num_rows()));
    for (int c = 0; c < column->num_chunks(); ++c) {
        auto chunk = column->chunk(c);
        if (auto arr = std::dynamic_pointer_cast<arrow::FloatArray>(chunk)) {
            for (int64_t i = 0; i < arr->length(); ++i) out.push_back(arr->Value(i));
        } else if (auto arr = std::dynamic_pointer_cast<arrow::DoubleArray>(chunk)) {
            for (int64_t i = 0; i < arr->length(); ++i) out.push_back(static_cast<float>(arr->Value(i)));
        } else {
            throw std::runtime_error("Unsupported " + name + " column type: " + chunk->type()->ToString());
        }
    }
    return out;
}

float clampf(float value, float lo, float hi) {
    return std::max(lo, std::min(hi, value));
}

template <typename T>
T pick(const T& a, const T& b, std::mt19937& rng) {
    std::bernoulli_distribution coin(0.5);
    return coin(rng) ? a : b;
}

} // namespace

HydraSignalTape load_hydra_signal_tape(
    const std::filesystem::path& path,
    const BarTape& bar_tape
) {
    auto table = read_parquet_table(path);
    auto times = extract_time_ms(table);
    auto directions = extract_i8(table, "direction");
    auto confidences = extract_f32(table, "confidence");
    auto regimes = extract_i8(table, "regime");

    if (times.size() != directions.size() ||
        times.size() != confidences.size() ||
        times.size() != regimes.size()) {
        throw std::runtime_error("Signal tape columns have mismatched lengths.");
    }

    std::unordered_map<int64_t, HydraSignal> by_time;
    by_time.reserve(times.size() * 2);
    for (size_t i = 0; i < times.size(); ++i) {
        by_time[times[i]] = HydraSignal{
            directions[i],
            clampf(confidences[i], 0.0f, 1.0f),
            regimes[i],
        };
    }

    HydraSignalTape tape;
    tape.signals.resize(bar_tape.bars.size());
    size_t matched = 0;
    for (size_t i = 0; i < bar_tape.bars.size(); ++i) {
        auto it = by_time.find(bar_tape.bars[i].time_ms);
        if (it != by_time.end()) {
            tape.signals[i] = it->second;
            matched++;
        }
    }

    std::cout << "[hydra] Signal tape loaded: rows=" << times.size()
              << " matched_bars=" << matched
              << " bars=" << bar_tape.bars.size()
              << std::endl;
    return tape;
}

std::string HydraExecutionParams::describe() const {
    std::ostringstream ss;
    ss << "HydraParams[" << param_id << "] gen=" << generation
       << " conf>=" << confidence_threshold
       << " SL=" << sl_atr_multiple << "xATR"
       << " TP=" << tp_atr_multiple << "xATR"
       << " hold=" << min_hold_bars << "-" << max_hold_bars
       << " risk=" << base_risk_fraction
       << " regimes=0x" << std::hex << static_cast<int>(allowed_regimes) << std::dec
       << " complexity=" << complexity();
    return ss.str();
}

std::string HydraExecutionParams::serialize_json() const {
    nlohmann::json j = {
        {"param_id", param_id},
        {"parent_id1", parent_id1},
        {"parent_id2", parent_id2},
        {"generation", generation},
        {"mutation_count", mutation_count},
        {"confidence_threshold", confidence_threshold},
        {"confidence_high", confidence_high},
        {"confidence_extreme", confidence_extreme},
        {"allowed_regimes", allowed_regimes},
        {"sl_atr_multiple", sl_atr_multiple},
        {"tp_atr_multiple", tp_atr_multiple},
        {"max_hold_bars", max_hold_bars},
        {"min_hold_bars", min_hold_bars},
        {"base_risk_fraction", base_risk_fraction},
        {"high_conf_risk_scale", high_conf_risk_scale},
        {"extreme_conf_risk_scale", extreme_conf_risk_scale},
        {"cooldown_bars", cooldown_bars},
    };
    return j.dump();
}

HydraExecutionParams HydraExecutionParams::deserialize_json(const std::string& json) {
    auto j = nlohmann::json::parse(json);
    HydraExecutionParams p;
    p.param_id = j.value("param_id", 0ULL);
    p.parent_id1 = j.value("parent_id1", 0ULL);
    p.parent_id2 = j.value("parent_id2", 0ULL);
    p.generation = j.value("generation", 0U);
    p.mutation_count = j.value("mutation_count", 0U);
    p.confidence_threshold = j.value("confidence_threshold", 0.50f);
    p.confidence_high = j.value("confidence_high", 0.75f);
    p.confidence_extreme = j.value("confidence_extreme", 0.90f);
    p.allowed_regimes = j.value("allowed_regimes", static_cast<uint8_t>(0b00000110));
    p.sl_atr_multiple = j.value("sl_atr_multiple", 1.5f);
    p.tp_atr_multiple = j.value("tp_atr_multiple", 2.5f);
    p.max_hold_bars = j.value("max_hold_bars", static_cast<int16_t>(30));
    p.min_hold_bars = j.value("min_hold_bars", static_cast<int16_t>(3));
    p.base_risk_fraction = j.value("base_risk_fraction", 0.01f);
    p.high_conf_risk_scale = j.value("high_conf_risk_scale", 1.25f);
    p.extreme_conf_risk_scale = j.value("extreme_conf_risk_scale", 1.50f);
    p.cooldown_bars = j.value("cooldown_bars", static_cast<int16_t>(5));
    return p;
}

int HydraExecutionParams::complexity() const {
    int value = 1;
    value += allowed_regimes == 0xFF ? 0 : 2;
    value += confidence_threshold > 0.65f ? 1 : 0;
    value += std::abs(tp_atr_multiple - sl_atr_multiple) > 2.0f ? 1 : 0;
    value += max_hold_bars > 80 ? 1 : 0;
    value += cooldown_bars > 20 ? 1 : 0;
    return value;
}

HydraExecutionParams random_hydra_params(std::mt19937& rng, uint64_t id) {
    std::uniform_real_distribution<float> conf(0.35f, 0.75f);
    std::uniform_real_distribution<float> high_gap(0.08f, 0.25f);
    std::uniform_real_distribution<float> sl(0.7f, 3.5f);
    std::uniform_real_distribution<float> rr(1.1f, 2.8f);
    std::uniform_real_distribution<float> risk(0.0025f, 0.025f);
    std::uniform_real_distribution<float> scale(1.05f, 1.75f);
    std::uniform_int_distribution<int> hold(8, 96);
    std::uniform_int_distribution<int> min_hold(1, 12);
    std::uniform_int_distribution<int> cooldown(1, 24);
    std::uniform_int_distribution<int> mask(1, 0b01111110);

    HydraExecutionParams p;
    p.param_id = id;
    p.confidence_threshold = conf(rng);
    p.confidence_high = std::min(0.92f, p.confidence_threshold + high_gap(rng));
    p.confidence_extreme = std::min(0.98f, p.confidence_high + high_gap(rng));
    p.allowed_regimes = static_cast<uint8_t>(mask(rng));
    p.sl_atr_multiple = sl(rng);
    p.tp_atr_multiple = std::min(8.0f, p.sl_atr_multiple * rr(rng));
    p.max_hold_bars = static_cast<int16_t>(hold(rng));
    p.min_hold_bars = static_cast<int16_t>(std::min<int>(min_hold(rng), p.max_hold_bars - 1));
    p.base_risk_fraction = risk(rng);
    p.high_conf_risk_scale = scale(rng);
    p.extreme_conf_risk_scale = std::max(p.high_conf_risk_scale, scale(rng));
    p.cooldown_bars = static_cast<int16_t>(cooldown(rng));
    return p;
}

HydraExecutionParams mutate_hydra_params(
    const HydraExecutionParams& parent,
    std::mt19937& rng,
    float rate
) {
    HydraExecutionParams p = parent;
    p.parent_id1 = parent.param_id;
    p.mutation_count++;
    std::uniform_real_distribution<float> coin(0.0f, 1.0f);
    std::normal_distribution<float> noise(0.0f, 1.0f);

    auto mutate_float = [&](float& value, float pct, float lo, float hi) {
        if (coin(rng) < rate) {
            value = clampf(value * (1.0f + noise(rng) * pct), lo, hi);
        }
    };

    mutate_float(p.confidence_threshold, 0.18f, 0.25f, 0.90f);
    mutate_float(p.confidence_high, 0.12f, p.confidence_threshold, 0.96f);
    mutate_float(p.confidence_extreme, 0.08f, p.confidence_high, 0.99f);
    mutate_float(p.sl_atr_multiple, 0.25f, 0.4f, 6.0f);
    mutate_float(p.tp_atr_multiple, 0.25f, 0.5f, 10.0f);
    mutate_float(p.base_risk_fraction, 0.30f, 0.001f, 0.05f);
    mutate_float(p.high_conf_risk_scale, 0.15f, 1.0f, 2.5f);
    mutate_float(p.extreme_conf_risk_scale, 0.15f, p.high_conf_risk_scale, 3.0f);

    if (coin(rng) < rate) {
        std::uniform_int_distribution<int> delta(-12, 12);
        p.max_hold_bars = static_cast<int16_t>(std::clamp<int>(p.max_hold_bars + delta(rng), 3, 240));
    }
    if (coin(rng) < rate) {
        std::uniform_int_distribution<int> delta(-3, 3);
        p.min_hold_bars = static_cast<int16_t>(std::clamp<int>(p.min_hold_bars + delta(rng), 1, p.max_hold_bars));
    }
    if (coin(rng) < rate) {
        std::uniform_int_distribution<int> delta(-4, 4);
        p.cooldown_bars = static_cast<int16_t>(std::clamp<int>(p.cooldown_bars + delta(rng), 0, 80));
    }
    if (coin(rng) < rate) {
        std::uniform_int_distribution<int> bit(1, 6);
        p.allowed_regimes ^= static_cast<uint8_t>(1u << bit(rng));
        if (p.allowed_regimes == 0) p.allowed_regimes = 0b00000110;
    }
    return p;
}

HydraExecutionParams crossover_hydra_params(
    const HydraExecutionParams& p1,
    const HydraExecutionParams& p2,
    std::mt19937& rng
) {
    HydraExecutionParams child;
    child.parent_id1 = p1.param_id;
    child.parent_id2 = p2.param_id;
    child.confidence_threshold = pick(p1.confidence_threshold, p2.confidence_threshold, rng);
    child.confidence_high = pick(p1.confidence_high, p2.confidence_high, rng);
    child.confidence_extreme = pick(p1.confidence_extreme, p2.confidence_extreme, rng);
    child.allowed_regimes = static_cast<uint8_t>(p1.allowed_regimes | p2.allowed_regimes);
    child.sl_atr_multiple = pick(p1.sl_atr_multiple, p2.sl_atr_multiple, rng);
    child.tp_atr_multiple = pick(p1.tp_atr_multiple, p2.tp_atr_multiple, rng);
    child.max_hold_bars = pick(p1.max_hold_bars, p2.max_hold_bars, rng);
    child.min_hold_bars = std::min<int16_t>(pick(p1.min_hold_bars, p2.min_hold_bars, rng), child.max_hold_bars);
    child.base_risk_fraction = pick(p1.base_risk_fraction, p2.base_risk_fraction, rng);
    child.high_conf_risk_scale = pick(p1.high_conf_risk_scale, p2.high_conf_risk_scale, rng);
    child.extreme_conf_risk_scale = pick(p1.extreme_conf_risk_scale, p2.extreme_conf_risk_scale, rng);
    child.cooldown_bars = pick(p1.cooldown_bars, p2.cooldown_bars, rng);
    child.generation = std::max(p1.generation, p2.generation) + 1;
    return child;
}

HydraStrategy::HydraStrategy(
    const HydraSignalTape& signal_tape,
    const HydraExecutionParams& params
)
    : signal_tape_(signal_tape)
    , params_(params) {}

void HydraStrategy::prepare(const Bar* tape, size_t tape_size) {
    atr_tape_.assign(tape_size, 0.0f);
    if (tape_size > 0) {
        constexpr float alpha = 1.0f / 14.0f;
        atr_tape_[0] = static_cast<float>(std::max(0.0, tape[0].high - tape[0].low));
        for (size_t i = 1; i < tape_size; ++i) {
            const double hl = tape[i].high - tape[i].low;
            const double hc = std::fabs(tape[i].high - tape[i - 1].close);
            const double lc = std::fabs(tape[i].low - tape[i - 1].close);
            const float tr = static_cast<float>(std::max({hl, hc, lc}));
            atr_tape_[i] = atr_tape_[i - 1] + alpha * (tr - atr_tape_[i - 1]);
        }
    }
    compile_signal_tape(tape, tape_size);
}

void HydraStrategy::compile_signal_tape(const Bar* /*bars*/, size_t n) {
    precomputed_signal_.assign(n, static_cast<uint8_t>(Signal::NONE));
    int16_t cooldown_remaining = 0;
    size_t long_count = 0;
    size_t short_count = 0;

    const size_t usable = std::min(n, signal_tape_.size());
    for (size_t i = 0; i < usable; ++i) {
        if (cooldown_remaining > 0) {
            cooldown_remaining--;
            continue;
        }

        const HydraSignal& sig = signal_tape_.at(i);
        if (sig.direction == HYDRA_NONE || sig.confidence < params_.confidence_threshold) {
            continue;
        }

        const uint8_t regime_value = static_cast<uint8_t>(std::max<int8_t>(0, sig.regime));
        const uint8_t regime_bit = regime_value < 8 ? static_cast<uint8_t>(1u << regime_value) : 0;
        if (regime_bit != 0 && (params_.allowed_regimes & regime_bit) == 0) {
            continue;
        }

        if (sig.direction == HYDRA_LONG) {
            precomputed_signal_[i] = static_cast<uint8_t>(Signal::BULLISH_CROSS);
            long_count++;
        } else if (sig.direction == HYDRA_SHORT) {
            precomputed_signal_[i] = static_cast<uint8_t>(Signal::BEARISH_CROSS);
            short_count++;
        }

        cooldown_remaining = std::max<int16_t>(0, params_.cooldown_bars);
    }

    if (long_count + short_count == 0) {
        std::cerr << "[hydra] warning: params " << params_.param_id
                  << " produced zero executable signals after gating."
                  << std::endl;
    }
}

Signal HydraStrategy::signal_at(size_t bar_idx) const {
    return (bar_idx < precomputed_signal_.size())
        ? static_cast<Signal>(precomputed_signal_[bar_idx])
        : Signal::NONE;
}

StrategyDecision HydraStrategy::decide(
    const MarketState& market,
    const AccountState& account,
    size_t bar_index
) {
    const float atr = (bar_index < atr_tape_.size() && atr_tape_[bar_index] > 1e-6f)
        ? atr_tape_[bar_index]
        : static_cast<float>(std::max(market.current_bar->high - market.current_bar->low, market.current_bar->close * 0.001));
    const HydraSignal sig = (bar_index < signal_tape_.size()) ? signal_tape_.at(bar_index) : HydraSignal{};
    return build_decision(sig, market.current_bar->close, atr, account.open_position_count);
}

StrategyDecision HydraStrategy::decide_with_intelligence(
    const MarketState& market,
    const AccountState& account,
    size_t bar_index,
    const IntelligenceState& /*intelligence*/
) {
    return decide(market, account, bar_index);
}

StrategyDecision HydraStrategy::build_decision(
    const HydraSignal& sig,
    double close,
    double atr,
    int open_positions
) const {
    StrategyDecision d;
    d.action = ActionType::HOLD;
    d.confidence = Confidence::NONE;

    if (open_positions > 0 || sig.direction == HYDRA_NONE || sig.confidence < params_.confidence_threshold) {
        return d;
    }

    if (sig.confidence >= params_.confidence_extreme) {
        d.confidence = Confidence::EXTREME;
        d.risk_fraction = params_.base_risk_fraction * params_.extreme_conf_risk_scale;
    } else if (sig.confidence >= params_.confidence_high) {
        d.confidence = Confidence::HIGH;
        d.risk_fraction = params_.base_risk_fraction * params_.high_conf_risk_scale;
    } else if (sig.confidence >= 0.50f) {
        d.confidence = Confidence::MEDIUM;
        d.risk_fraction = params_.base_risk_fraction;
    } else {
        d.confidence = Confidence::LOW;
        d.risk_fraction = params_.base_risk_fraction;
    }

    d.preferred_regime = static_cast<Regime>(std::max<int8_t>(0, sig.regime));
    d.expected_hold_bars = static_cast<uint16_t>(std::max<int16_t>(1, params_.max_hold_bars));
    d.minimum_hold_bars = static_cast<uint16_t>(
        std::clamp<int>(params_.min_hold_bars, 1, params_.max_hold_bars)
    );

    const double safe_atr = std::max(atr, close * 0.0001);
    if (sig.direction == HYDRA_LONG) {
        d.action = ActionType::OPEN_LONG;
        d.stop_loss = close - safe_atr * params_.sl_atr_multiple;
        d.take_profit = close + safe_atr * params_.tp_atr_multiple;
    } else if (sig.direction == HYDRA_SHORT) {
        d.action = ActionType::OPEN_SHORT;
        d.stop_loss = close + safe_atr * params_.sl_atr_multiple;
        d.take_profit = close - safe_atr * params_.tp_atr_multiple;
    }

    d.stop_width_multiplier = params_.sl_atr_multiple / 2.0f;
    d.take_profit_multiplier = params_.tp_atr_multiple / 3.0f;
    d.context_pressure = clampf(sig.confidence, 0.0f, 1.0f);
    d.entry_aggression = clampf(sig.confidence, 0.0f, 1.0f);
    return d;
}

} // namespace aphelion
