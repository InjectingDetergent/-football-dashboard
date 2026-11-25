"""Fit regularised goal models and simulate the remaining league programme."""

from datetime import date

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln


SIMULATIONS = 20_000
HALF_LIFE_DAYS = 90
REGULARISATION = 3.0


def fit_model(matches, teams, xg_weight):
    index = {name: i for i, name in enumerate(teams)}
    home = np.array([index[match[2]] for match in matches])
    away = np.array([index[match[3]] for match in matches])
    goals = np.array([match[4:6] for match in matches], dtype=float)
    targets = goals.copy()
    for i, match in enumerate(matches):
        if len(match) >= 9 and all(value is not None for value in match[7:9]):
            targets[i] = (1 - xg_weight) * goals[i] + xg_weight * np.array(match[7:9])
    cutoff = date.fromisoformat(matches[-1][0])
    ages = np.array([(cutoff - date.fromisoformat(match[0])).days for match in matches])
    weights = np.exp2(-ages / HALF_LIFE_DAYS)
    count = len(teams)

    def objective(parameters):
        attack = parameters[2:2 + count]
        defence = parameters[2 + count:]
        log_home = parameters[0] + parameters[1] + attack[home] + defence[away]
        log_away = parameters[0] + attack[away] + defence[home]
        home_mean, away_mean = np.exp(log_home), np.exp(log_away)
        loss = np.sum(weights * (home_mean - targets[:, 0] * log_home +
                                 away_mean - targets[:, 1] * log_away))
        loss += REGULARISATION * np.sum(parameters[2:] ** 2) / 2
        dh = weights * (home_mean - targets[:, 0])
        da = weights * (away_mean - targets[:, 1])
        gradient = np.concatenate((
            [np.sum(dh + da), np.sum(dh)],
            np.bincount(home, weights=dh, minlength=count) +
            np.bincount(away, weights=da, minlength=count),
            np.bincount(away, weights=dh, minlength=count) +
            np.bincount(home, weights=da, minlength=count)))
        gradient[2:] += REGULARISATION * parameters[2:]
        return loss, gradient

    initial = np.zeros(2 + 2 * count)
    initial[0] = np.log(max(np.average(targets[:, 1], weights=weights), .1))
    initial[1] = np.log(max(np.average(targets[:, 0], weights=weights), .1)) - initial[0]
    fitted = minimize(objective, initial, jac=True, method="L-BFGS-B",
                      bounds=[(-3, 3), (-1.5, 1.5)] + [(-2, 2)] * (2 * count))
    if not fitted.success or not np.all(np.isfinite(fitted.x)):
        raise ValueError(f"Season model fitting failed: {fitted.message}")
    return fitted.x


def match_rates(parameters, teams, matches):
    index = {name: i for i, name in enumerate(teams)}
    home = np.array([index[match[2]] for match in matches], dtype=int)
    away = np.array([index[match[3]] for match in matches], dtype=int)
    count = len(teams)
    attack, defence = parameters[2:2 + count], parameters[2 + count:]
    return np.column_stack((
        np.exp(parameters[0] + parameters[1] + attack[home] + defence[away]),
        np.exp(parameters[0] + attack[away] + defence[home])))


def select_model(matches, teams):
    split = int(len(matches) * .75)
    cutoff = matches[split][0]
    training = [match for match in matches if match[0] < cutoff]
    holdout = [match for match in matches if match[0] >= cutoff]
    coverage = sum(len(match) >= 9 and all(value is not None for value in match[7:9])
                   for match in matches)
    candidates = [0.0, .7] if coverage else [0.0]
    validation = []
    if len(training) >= len(teams) * 2 and len(holdout) >= 10:
        observed = np.array([match[4:6] for match in holdout])
        for weight in candidates:
            parameters = fit_model(training, teams, weight)
            rates = match_rates(parameters, teams, holdout)
            loss = np.mean(np.sum(rates - observed * np.log(rates) + gammaln(observed + 1), axis=1))
            validation.append({"xg_weight": weight, "score_log_loss": float(loss)})
        chosen = min(validation, key=lambda entry: entry["score_log_loss"])["xg_weight"]
    else:
        chosen = 0.0
    return chosen, {"training_matches": len(training), "holdout_matches": len(holdout),
                    "cutoff": cutoff, "models": validation}


def simulate_season(group, simulations=SIMULATIONS, seed=20261125):
    matches = group["matches"]
    teams = sorted({name for match in matches for name in match[2:4]})
    count = len(teams)
    played = [match for match in matches if match[6] == "Played"]
    if len(played) < count * 2:
        return {"unavailable": "At least two completed matches per club on average are needed to fit this model."}
    expected = {(home, away) for home in teams for away in teams if home != away}
    pairings = {(match[2], match[3]) for match in matches}
    if pairings != expected or len(matches) != len(expected):
        return {"unavailable": "The fixture export does not contain a complete, unique home-and-away league programme."}
    remaining = [match for match in matches if match[6] != "Played"]
    supported = {"To be played", "Postponed"}
    if any(match[6] not in supported for match in remaining):
        return {"unavailable": "The fixture export contains an unrecognised status. Review it before simulating."}

    index = {name: i for i, name in enumerate(teams)}
    current = np.zeros(count, dtype=int)
    gf = np.zeros(count, dtype=int)
    ga = np.zeros(count, dtype=int)
    games = np.zeros(count, dtype=int)
    for match in played:
        home, away = index[match[2]], index[match[3]]
        hg, ag = match[4:6]
        current[home] += 3 * (hg > ag) + (hg == ag)
        current[away] += 3 * (ag > hg) + (hg == ag)
        gf[home] += hg
        ga[away] += hg
        gf[away] += ag
        ga[home] += ag
        games[[home, away]] += 1
    for name, adjustment in group.get("points_adjustments", {}).items():
        if name in index:
            current[index[name]] += adjustment
    weight, validation = select_model(played, teams)
    parameters = fit_model(played, teams, weight)
    rates = match_rates(parameters, teams, remaining)
    rng = np.random.default_rng(seed)
    final_points = np.tile(current, (simulations, 1))
    final_gf = np.tile(gf, (simulations, 1))
    final_gd = np.tile(gf - ga, (simulations, 1))
    for match, (home_rate, away_rate) in zip(remaining, rates):
        home, away = index[match[2]], index[match[3]]
        hg = rng.poisson(home_rate, simulations)
        ag = rng.poisson(away_rate, simulations)
        final_points[:, home] += 3 * (hg > ag) + (hg == ag)
        final_points[:, away] += 3 * (ag > hg) + (hg == ag)
        final_gf[:, home] += hg
        final_gf[:, away] += ag
        final_gd[:, home] += hg - ag
        final_gd[:, away] += ag - hg
    order = np.lexsort((rng.random(final_points.shape), -final_gf, -final_gd, -final_points), axis=1)
    frequencies = np.zeros((count, count), dtype=int)
    for position in range(count):
        frequencies[:, position] = np.bincount(order[:, position], minlength=count)
    if not np.all(frequencies.sum(axis=0) == simulations) or not np.all(frequencies.sum(axis=1) == simulations):
        raise ValueError("Simulated position totals failed reconciliation")
    current_order = sorted(range(count), key=lambda i: (-current[i], -(gf[i] - ga[i]), -gf[i], teams[i]))
    positions = {team: position + 1 for position, team in enumerate(current_order)}
    rows = []
    for i, name in enumerate(teams):
        lower, upper = np.quantile(final_points[:, i], [.1, .9], method="inverted_cdf")
        rows.append({
            "team": name, "current_position": positions[i], "played": int(games[i]),
            "current_points": int(current[i]), "mean_points": float(np.mean(final_points[:, i])),
            "points_low": int(lower), "points_high": int(upper),
            "mean_position": float(np.dot(frequencies[i], np.arange(1, count + 1)) / simulations),
            "position_counts": frequencies[i].tolist(),
        })
    return {
        "simulations": simulations, "seed": seed, "as_of": played[-1][0],
        "played": len(played), "remaining": len(remaining),
        "overdue": sum(match[0] <= played[-1][0] for match in remaining),
        "xg_matches": sum(len(match) >= 9 and all(value is not None for value in match[7:9]) for match in played),
        "xg_weight": weight, "half_life_days": HALF_LIFE_DAYS,
        "regularisation": REGULARISATION, "validation": validation, "teams": rows,
    }
