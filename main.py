import sys
import subprocess
import argparse

def run_generator(args):
    cmd = [sys.executable, "src/quote_generator.py"] + args
    subprocess.run(cmd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Quotes Engine Management Script")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Subparser for generate
    gen_parser = subparsers.add_parser("generate", help="Generate structured quotes")
    gen_parser.add_argument("--num_quotes", type=int, default=5)
    gen_parser.add_argument("--chaos", type=float, help="0..1 how unhinged the quotes get")
    gen_parser.add_argument("--rate", action="store_true", help="Rate quotes interactively")
    gen_parser.add_argument("--raw", action="store_true", help="Print only the quote text")
    gen_parser.add_argument("--theme", type=str, default="general", help="Theme to use for generation")
    gen_parser.add_argument("--paragraph", action="store_true", help="Generate a full paragraph of wisdom")
    gen_parser.add_argument("--sentences", type=int, default=8, help="Number of sentences in the paragraph")
    gen_parser.add_argument("--svg", action="store_true", help="Export the result to a stylish SVG image")
    gen_parser.add_argument("--image", action="store_true", help="Export the result to a professional PNG image")

    args, unknown = parser.parse_known_args()

    if args.command == "generate":
        pass_args = []
        if args.num_quotes: pass_args += ["--num_quotes", str(args.num_quotes)]
        if args.chaos is not None: pass_args += ["--chaos", str(args.chaos)]
        if args.rate: pass_args.append("--rate")
        if args.raw: pass_args.append("--raw")
        if args.theme: pass_args += ["--theme", args.theme]
        if args.paragraph: pass_args.append("--paragraph")
        if args.sentences: pass_args += ["--sentences", str(args.sentences)]
        if args.svg: pass_args.append("--svg")
        if args.image: pass_args.append("--image")
        pass_args.extend(unknown)
        run_generator(pass_args)
    else:
        parser.print_help()
