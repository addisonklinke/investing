def parse_period(period):
    """Convert various financial periods to number of days

    :param int or str period: Number of days for the return window or one of
        the following keyword strings
            * daily
            * monthly
            * quarterly
            * yearly
            * n-year
    :return int days:
    """
    if isinstance(period, int):
        days = period
    elif isinstance(period, str):
        if period == 'daily':
            days = 1
        elif period == 'monthly':
            days = 30
        elif period == 'quarterly':
            days = 91
        elif period == 'yearly':
            days = 365
        elif period.endswith('year') and '-' in period:
            days = int(period.split('-')[0]) * 365
        else:
            raise ValueError(f'{period} string does not match supported formats')
    else:
        raise ValueError(f'Exepcted type int or str, but received {type(period)}')
    return days
