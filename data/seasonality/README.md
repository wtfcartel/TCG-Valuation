# Seasonality (synthetic, demonstrative)

`season_profile.csv` is the demonstration season pattern given for the interview: slow growth Jan–Feb, heavy growth
Mar–May, no growth Jun–Jul, peak Aug–Nov. December was not specified and is assumed to wind down to the Christmas
break. `activity_index` is work available relative to an average month (1.0).

`units.csv` describes four invented operating units (a crew with its allocated plant). Every figure is invented to
exercise the calculation. None of it describes Green Turf.

`seasonal_sensitivity` dampens the season for steadier work: 1.0 follows the index fully, 0.5 moves half as much.
