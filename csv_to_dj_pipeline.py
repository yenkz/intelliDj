# Shim — logic now lives in intellidj.pipeline.candidates
from intellidj.pipeline.candidates import (  # noqa: F401
    clean_track_name,
    simplify_for_search,
    normalize_artist,
    infer_style,
    build_candidates_dataframe,
    default_output_for_input,
    main,
    DEFAULT_INPUT_FILE,
)

if __name__ == "__main__":
    import argparse
    from intellidj.pipeline.candidates import main, default_output_for_input, DEFAULT_INPUT_FILE

    parser = argparse.ArgumentParser(description="Generate dj_candidates.csv from a Spotify export")
    parser.add_argument("--input", default=DEFAULT_INPUT_FILE)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    output_file = args.output or default_output_for_input(args.input)
    main(args.input, output_file)
