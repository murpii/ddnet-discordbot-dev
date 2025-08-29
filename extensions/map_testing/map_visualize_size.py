#!/usr/bin/env python3
# Generates plots that visualize which images/sounds take up how much of the map size.
# Command line parameter: MAP_PATH
#
# Requires the tw_map_v4 module which is the map.ksy kaitai module for Python.
# References:
# 1. https://github.com/heinrich5991/libtw2/blob/master/doc/map_v4.ksy
# 2. https://doc.kaitai.io/stream_api.html
#
# Author: Patiga
# License: MIT

from tw_map_v4 import TwMapV4
import matplotlib.pyplot as plt
import numpy as np
import io

def visualize_from_bytes(data) -> io.BytesIO:
    map = TwMapV4.from_bytes(data)

    image_names = []
    image_sizes = []
    sound_names = []
    sound_sizes = []

    total = 0
    for item in map.items:
        if item.type_id == TwMapV4.ItemKind.image:
            image = item.content
            image_names.append(f"{image.name.string.strip('\0')} ({item.id})")
            if image.data_index is not TwMapV4.Optional.not_set:
                image_sizes.append(len(map._raw__raw_data_items[image.data_index]))
            else:
                image_sizes.append(0)
        elif item.type_id == TwMapV4.ItemKind.sound:
            sound = item.content
            sound_names.append(f"{sound.name.string.strip('\0')} ({item.id})")
            if sound.data_index is not TwMapV4.Optional.not_set:
                sound_sizes.append(len(map._raw__raw_data_items[sound.data_index]))
            else:
                sound_sizes.append(0)

    # https://stackoverflow.com/a/1094933
    def sizeof_fmt(num, suffix="B"):
        for unit in ("", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"):
            if abs(num) < 1024.0:
                return f"{num:3.1f}{unit}{suffix}"
            num /= 1024.0
        return f"{num:.1f}Yi{suffix}"

    total_images_size = sum(image_sizes)
    total_sounds_size = sum(sound_sizes)
    total_map_size = map.header.size
    other = total_map_size - total_images_size - total_sounds_size

    fig, ((total, single_items), (images, sounds)) = plt.subplots(2, 2)
    total.set_title("Total")
    total.pie(
        [total_images_size, total_sounds_size, other],
        labels=["Images", "Sounds", "Remaining"],
        autopct='%1.1f%%',
    )
    images.set_title("Images")
    images.pie(image_sizes, labels=image_names, autopct='%1.1f%%')
    sounds.set_title("Sounds")
    sounds.pie(sound_sizes, labels=sound_names, autopct='%1.1f%%')

    items = []
    for sizes, names, prefix in [(image_sizes, image_names, "I"), (sound_sizes, sound_names, "S")]:
        for size, name in zip(sizes, names):
            items.append((size, f"[{prefix}] {name}"))
    items = list(reversed(sorted(items, key=lambda item: item[0])))
    items = items[:min(10, len(items))]
    y_pos = np.arange(len(items))
    single_items.set_title("Items")
    bars = single_items.barh(
        y_pos,
        [size for size, _ in items],
        align='center',
    )
    single_items.bar_label(bars, fmt=sizeof_fmt)
    single_items.set_yticks(
        y_pos,
        labels=[name for _, name in items],
    )
    single_items.invert_yaxis()  # labels read top-to-bottom
    plt.subplots_adjust(left=0.1, right=0.95, top=0.9, bottom=0.1, hspace=0.4, wspace=0.3)

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    return buf
