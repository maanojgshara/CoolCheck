"""The electricity term of the can't-cool-down index (Guide §A11 decision 9; docs/design/risk_score.md §8).

EMA table T3.5 gives the average monthly household electricity use (kWh per account) by planning area and dwelling type.
For the 1-room / 2-room rows, a year's hot-month ratio is mean(Apr, May, Jun of Y) / mean(Nov and Dec of Y - 1, Jan and
Feb of Y), and it needs all seven months. An area's value is the mean of its 2022, 2023 and 2024 ratios when all three
exist. A smaller rise "may indicate" less air-con use, never more than that.
"""
from statistics import mean

HOT = ((0, 4), (0, 5), (0, 6))
COOL = ((-1, 11), (-1, 12), (0, 1), (0, 2))
VALUE_YEARS = (2022, 2023, 2024)
FIRST_READING_YEARS = tuple(range(2015, 2025))


def year_ratio(monthly, year):
    """Hot-month ratio for one year from {(year, month): kWh}, or None unless all seven months are present."""
    hot = [monthly.get((year + dy, m)) for dy, m in HOT]
    cool = [monthly.get((year + dy, m)) for dy, m in COOL]
    if any(v is None for v in hot + cool):
        return None
    return mean(hot) / mean(cool)


def ratios(monthly, years):
    """{year: ratio} for the years that have all seven months."""
    got = {y: year_ratio(monthly, y) for y in years}
    return {y: r for y, r in got.items() if r is not None}


def three_year_mean(by_year, years=VALUE_YEARS):
    """Mean of the yearly ratios when every year in years has one, else None."""
    if any(y not in by_year for y in years):
        return None
    return mean(by_year[y] for y in years)


def mean_over_area_years(by_area, years=FIRST_READING_YEARS):
    """(mean of every area-year ratio, number of area-years) over the given years; by_area is {area: {year: ratio}}."""
    vals = [r for yr in by_area.values() for y, r in yr.items() if y in years]
    return (mean(vals) if vals else None), len(vals)


def pooled_ratio(monthly, years=FIRST_READING_YEARS):
    """Mean of all hot-month values over the years, over the mean of all their cool-month values (months present)."""
    hot = [monthly[(y + dy, m)] for y in years for dy, m in HOT if (y + dy, m) in monthly]
    cool = [monthly[(y + dy, m)] for y in years for dy, m in COOL if (y + dy, m) in monthly]
    return (mean(hot) / mean(cool)) if hot and cool else None
