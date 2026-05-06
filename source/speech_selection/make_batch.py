import glob
import json
import os
from optparse import OptionParser

import numpy as np
import pandas as pd


def main():
    usage = "%prog"
    parser = OptionParser(usage=usage)
    parser.add_option(
        "--indir",
        type=str,
        default="01_data/intermediate/text/selected_speech/",
        help="Input dir: default=%default",
    )
    parser.add_option(
        "--basedir",
        type=str,
        default="01_data/intermediate/text/for_annotation_climate/rounds/",
        help="Base output dir: default=%default",
    )
    parser.add_option(
        "--per-batch",
        type=int,
        default=120,
        help="Number of items per batch: default=%default",
    )
    parser.add_option(
        "--start",
        type=int,
        default=0,
        help="Start index: default=%default",
    )
    parser.add_option(
        "--min-congress",
        type=int,
        default=92,
        help="Minimum congress number to include: default=%default",
    )

    (options, args) = parser.parse_args()

    indir = options.indir
    basedir = options.basedir
    items_per_batch = options.per_batch
    start = options.start
    min_congress = options.min_congress

    files = sorted(glob.glob(os.path.join(indir, "*.jsonlist")))

    np.random.seed(0)
    all_lines = []
    for infile in files:
        with open(infile) as f:
            for raw_line in f:
                line = json.loads(raw_line)
                congress_num = int(line["infile"][9:12])
                if congress_num >= min_congress:
                    all_lines.append(line)

    print(f"Total segments after filtering: {len(all_lines)}")

    order = np.arange(len(all_lines))
    np.random.shuffle(order)

    total_items = items_per_batch
    if start + total_items > len(all_lines):
        raise ValueError(
            f"Not enough items: requested up to index {start + total_items - 1}, "
            f"but only {len(all_lines)} items are available."
        )

    outlines = []
    for i in range(total_items):
        index = order[start + i]
        line = all_lines[index]
        segment_id = line["id"]
        congress_str = line["infile"][9:12]
        congress_num = int(congress_str)
        year = 1873 + (congress_num - 43) * 2
        text = line["text"]
        outline = [segment_id, congress_str, year, text]
        outlines.append(outline)

    outdir = os.path.join(basedir, str(start))
    if not os.path.exists(outdir):
        os.makedirs(outdir)

    df = pd.DataFrame(outlines, columns=["id", "congress", "year", "text"])
    df.to_csv(os.path.join(outdir, "1.csv"), index=False)

    print(f"Saved {total_items} items to {os.path.join(outdir, '1.csv')}")
    print(f"Next start: {start + total_items}")
    with open(os.path.join(outdir, "next_start.txt"), "w") as f:
        f.write(f"Next start: {start + total_items}")


if __name__ == "__main__":
    main()