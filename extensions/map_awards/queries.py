def maps_released_in_year(year: int) -> str:
    return f"""
    SELECT *
    FROM record_maps
    WHERE Timestamp BETWEEN '{year}-01-01' AND '{year + 1}-01-01'
    ORDER BY Timestamp ASC;
    """


def total_finishes_nonfun(year: int) -> str:
    return f"""
    SELECT COUNT(*) AS row_count
    FROM record_race rr
    JOIN record_maps rm ON rr.Map = rm.Map
    WHERE rr.Timestamp >= '{year}-01-01'
      AND rr.Timestamp < '{year + 1}-01-01'
      AND (
            rm.Server <> 'Fun'
            OR rm.Map IN (
                'Castle Echos',
                'KingsLeap',
                'Linear II',
                'Good Movement',
                'IWannaBeatTheMap',
                'IWannaBeatTheMap2',
                'MultiFAT',
                'Flappy Bird',
                'Edge Jump Pro'
            )
      );
    """


def total_finishes_all(year: int) -> str:
    return f"""
    SELECT COUNT(*) AS row_count
    FROM record_race
    WHERE Timestamp BETWEEN '{year}-01-01' AND '{year + 1}-01-01';
    """


def top_5_most_finished_maps(year: int) -> str:
    return f"""
    SELECT rr.Map, COUNT(*) AS finishes
    FROM record_race rr
    JOIN record_maps rm ON rr.Map = rm.Map
    WHERE rr.Timestamp >= '{year}-01-01'
      AND rr.Timestamp < '{year + 1}-01-01'
      AND (
            rm.Server <> 'Fun'
            OR rm.Map IN (
                'Castle Echos',
                'KingsLeap',
                'Linear II',
                'Good Movement',
                'IWannaBeatTheMap',
                'IWannaBeatTheMap2',
                'MultiFAT',
                'Flappy Bird',
                'Edge Jump Pro'
            )
      )
    GROUP BY rr.Map
    ORDER BY finishes DESC
    LIMIT 5;
    """


def top_player_of_the_year() -> str:
    return """
           SELECT Name, Points
           FROM record_points
           ORDER BY Points DESC
           LIMIT 1; \
           """


