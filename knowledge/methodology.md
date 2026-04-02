# Risk Score Methodology

Each event is scored as:
risk = (duration_hours ^ 0.75) x event_weight x flag_multiplier x offshore_bonus

Event weights: ENCOUNTER=5.0 (transshipment), GAP=3.2 (dark activity), LOITERING=2.0 (staging)
Flag multipliers: RUS=2.8, IRN=2.4, SYR=2.0, PRK=3.0, LBR=1.3, PAN=1.2, MHL=1.2, others=1.0
Offshore bonus: 1.4x for loitering events in central/eastern Med (lon>15, lat within 8 of 36N)
Non-linear duration exponent (0.75) prevents single extreme events from dominating.
