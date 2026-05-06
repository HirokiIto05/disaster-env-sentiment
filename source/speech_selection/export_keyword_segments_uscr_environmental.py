import json
import os
from collections import Counter
from glob import glob
from optparse import OptionParser

from tqdm import tqdm

try:
    from speech_selection.common import match_tokens
    from speech_selection.query_terms import environmental
except ImportError:
    from common import match_tokens
    from query_terms import environmental


def load_existing_pairs(outfile):
    existing_pairs = set()
    if not os.path.exists(outfile):
        return existing_pairs

    with open(outfile) as f:
        for raw_line in f:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            line = json.loads(raw_line)
            existing_pairs.add((line["infile"], line["id"]))
    return existing_pairs


def load_progress(progress_file):
    if not os.path.exists(progress_file):
        return set()
    with open(progress_file) as f:
        data = json.load(f)
    return set(data.get("completed_congress_files", []))


def save_progress(progress_file, completed_files):
    tmp_file = progress_file + ".tmp"
    with open(tmp_file, "w") as f:
        json.dump({"completed_congress_files": sorted(completed_files)}, f, ensure_ascii=False, indent=2)
    os.replace(tmp_file, progress_file)


def main():
    usage = "%prog"
    parser = OptionParser(usage=usage)
    parser.add_option(
        "--uscr-dir",
        type=str,
        default="01_data/intermediate/text/uscr_tokenized",
        help="USCR tokenized directory: default=%default",
    )
    parser.add_option(
        "--outfile",
        type=str,
        default="01_data/intermediate/text/selected_speech/keyword_segments_uscr_environmental.jsonlist",
        help="Output file: default=%default",
    )
    parser.add_option(
        "--use-sents",
        action="store_true",
        default=False,
        help="Use sentence text if available: default=%default",
    )
    parser.add_option(
        "--min-congress",
        type=int,
        default=1,
        help="Minimum congress number to include: default=%default",
    )
    parser.add_option(
        "--no-resume",
        action="store_true",
        default=False,
        help="Ignore existing output/progress and start fresh: default=%default",
    )
    (options, args) = parser.parse_args()

    uscr_dir = options.uscr_dir
    outfile = options.outfile
    use_sents = options.use_sents
    min_congress = options.min_congress
    no_resume = options.no_resume

    outdir = os.path.dirname(outfile)
    if outdir and not os.path.exists(outdir):
        os.makedirs(outdir)

    files = sorted(glob(os.path.join(uscr_dir, "speeches_*.jsonlist")))
    files = [
        f
        for f in files
        if int(os.path.basename(f).split(".")[0].split("_")[-1]) >= min_congress
    ]
    print(len(files))

    chunk_lengths = Counter()
    total_count = 0
    progress_file = outfile + ".progress.json"

    if no_resume:
        if os.path.exists(outfile):
            os.remove(outfile)
        if os.path.exists(progress_file):
            os.remove(progress_file)

    existing_pairs = load_existing_pairs(outfile)
    completed_files = load_progress(progress_file)

    for infile in files:
        basename = os.path.basename(infile).split(".")[0]
        if basename in completed_files:
            print(f"skip {basename} (already completed)")
            continue

        with open(infile) as f:
            lines = [json.loads(line) for line in f]

        print(basename, len(lines))
        congress_outlines = []
        for line in tqdm(lines):
            tokenized_sents = line["tokens"]
            if use_sents and "sents" in line:
                sents = line["sents"]
            else:
                sents = [" ".join(sent) for sent in tokenized_sents]
            assert len(sents) == len(tokenized_sents)
            line_id = line["id"]

            n_sents = len(tokenized_sents)
            for sent_i, tokens in enumerate(tokenized_sents):
                if match_tokens(tokens, environmental):
                    chunk = " ".join(sents[max(0, sent_i - 3) : min(n_sents, sent_i + 4)])
                    segment_id = f"{line_id}_{sent_i}"
                    segment_key = (basename, segment_id)
                    if segment_key in existing_pairs:
                        continue

                    outline = {"infile": basename, "id": segment_id, "text": chunk}
                    congress_outlines.append(outline)
                    existing_pairs.add(segment_key)
                    chunk_lengths.update([len(chunk.split())])
                    total_count += 1

        with open(outfile, "a") as f_out:
            for line in congress_outlines:
                f_out.write(json.dumps(line) + "\n")

        completed_files.add(basename)
        save_progress(progress_file, completed_files)
        print(f"wrote {len(congress_outlines)} segments for {basename}")

    print(total_count)


if __name__ == "__main__":
    main()
