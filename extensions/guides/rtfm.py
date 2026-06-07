import numpy as np
import pandas

URL = "https://ddnet.org/settingscommands/"


def floats_to_int(dictionary: dict) -> None:
    for key, val in dictionary.items():
        if isinstance(val, float) and not np.isnan(val) and val == int(val):
            dictionary[key] = int(val)
        elif isinstance(val, dict):
            floats_to_int(val)


def load_tables() -> list:
    return pandas.read_html(URL)


def get_setting_names(tables: list) -> list[str]:
    setting_names = []
    for table in tables:
        for column in ['Setting', 'Command', 'Tuning']:
            if column in table.columns:
                setting_names.extend(table[column].dropna().tolist())
    return setting_names


def get_setting_description(tables: list, setting: str) -> dict | None:
    for table in tables:
        table_copy = table.copy()
        table_copy.set_index(table_copy.columns[0], inplace=True)
        if setting in table_copy.index:
            return table_copy.loc[setting].to_dict()
    return None
