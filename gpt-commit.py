#!/usr/bin/env python3

import argparse
import asyncio
import os
import subprocess
import sys
import configparser
import logging

from icecream import ic
# import openai
from openai import AsyncOpenAI

sys.path.append(os.path.dirname(__file__))
import logging_utils

logger = logging.getLogger(__name__)


### Constants
DIFF_PROMPT = (
    "Generate succinct, conscise, and high-quality summaries of the "
    "following code changes. High quality summaries remove unnecessary, "
    "redundant, or obvious details. Use clear, precise, and non-self "
    "referential language."
    "\n\nCode changes:\n"
)
COMMIT_TITLE_PROMPT = (
    "Using the provided code change summaries, write one "
    "repository commit message in the Conventional Commits specification "
    "v1.0.0 format. The commit MUST be prefixed with a type followed by "
    "the REQUIRED terminal colon and space. Then, a description MUST "
    "immediately follow the colon and space after the type prefix. The "
    "description is a short summary of the code changes, e.g., `fix: array "
    "parsing issue when multiple spaces were contained in string`\n\nCode change summaries:\n"
)
COMMIT_BODY_PROMPT = (
    "From the following commit type, description, and code change summaries, "
    "write a longer commit body according to the Conventional Commits "
    "specification v1.0.0 standard. A commit body follows the commit "
    "description and provdes additional information about the code changes. A "
    "commit body is free-form and MAY consist of any number of newline "
    "separated paragraphs. A commit body excludes the type and description."
)
PROMPT_CUTOFF = 10000
## Module configuration
# Configuration file
CONFIG_FOLDER = "config"
CONFIG_FILENAME = "api_keys.ini"


# API key is stored inside config file
config = configparser.ConfigParser()
script_dir = os.path.dirname(os.path.abspath(__file__))
ini_path = os.path.join(script_dir, CONFIG_FOLDER, CONFIG_FILENAME)
config.read(ini_path)
openai_gpt35key = config.get("openai", "gpt35")

client = AsyncOpenAI(api_key = openai_gpt35key)

def parse_diff(diff):
    file_diffs = diff.split("\ndiff")
    file_diffs = [file_diffs[0]] + [
        "\ndiff" + file_diff for file_diff in file_diffs[1:]
    ]
    chunked_file_diffs = []
    for file_diff in file_diffs:
        [head, *chunks] = file_diff.split("\n@@")
        chunks = ["\n@@" + chunk for chunk in reversed(chunks)]
        chunked_file_diffs.append((head, chunks))
    return chunked_file_diffs


def assemble_diffs(parsed_diffs, cutoff):
    # create multiple well-formatted diff strings, each being shorter than cutoff
    assembled_diffs = [""]

    def add_chunk(chunk):
        if len(assembled_diffs[-1]) + len(chunk) <= cutoff:
            assembled_diffs[-1] += "\n" + chunk
            return True
        else:
            assembled_diffs.append(chunk)
            return False

    for head, chunks in parsed_diffs:
        if not chunks:
            add_chunk(head)
        else:
            add_chunk(head + chunks.pop())
        while chunks:
            if not add_chunk(chunks.pop()):
                assembled_diffs[-1] = head + assembled_diffs[-1]
    return assembled_diffs


async def complete(prompt):
    chatml_prompt = [
            {
                "role": "system",
                "content": "You are a senior software engineer at a software development company. Your current assignment is to perform mundane administrative tasks relating to maintaining a well-organized company github code repositories",
            },
            {"role": "user", "content": prompt[: PROMPT_CUTOFF + 100]},
        ]
    if args.dry_run: ic(chatml_prompt)
    completion_resp = await client.chat.completions.create(
        model="gpt-3.5-turbo",
        temperature=0.3,
        messages=chatml_prompt,
        max_tokens=128,
    )
    completion = completion_resp.choices[0].message.content.strip()
    if args.dry_run: ic(completion)  # DEBUG
    return completion


# 6. if args.dry_run:
#           print(commit_message)
#       else:
#           exit(commit(commit_message, commit_body))
def commit(message, body):
    # will ignore message if diff is empty
    commit_command = [
        "git",
        "commit",
        "--edit",
        "--message",
        message,
        "--message",
        body,
    ]
    return subprocess.run(commit_command).returncode

# 5. try:
#       ...
#       commit_body = await generate_commit_body(commit_message, code_change_summaries)
async def generate_commit_body(type_and_description, summaries):
    assert summaries
    result = await complete(
        f"{COMMIT_BODY_PROMPT}\n\n"
        f"Type: {type_and_description}\n"
        f"Code change summaries: {summaries}\n\n"
    )
    return result


# 4. try:
#       ...
#       commit_message = await generate_commit_message(code_change_summaries)
async def generate_commit_message(summaries):
    return await summarize_summaries("\n".join(summaries))

async def summarize_summaries(summaries):
    assert summaries
    result = await complete(COMMIT_TITLE_PROMPT + "\n\n" + summaries + "\n\n")
    return result


# 3. try:
#       ...
#       code_change_summaries = await summarize_changes(diff)
async def summarize_changes(diff):
    if not diff:
        # no files staged or only whitespace diffs
        return "Fix whitespace"

    assembled_diffs = assemble_diffs(parse_diff(diff), PROMPT_CUTOFF)
    diff_list = [diff for diff in assembled_diffs]
    summaries = await asyncio.gather(
        *[summarize_diff(diff) for diff in assembled_diffs]
    )
    return summaries

async def summarize_diff(diff):
    assert diff
    result = await complete(DIFF_PROMPT + "\n\n" + diff + "\n\n")
    return result


# 2. try:
#       diff = get_diff()
def get_diff():
    arguments = [
        "git",
        "--no-pager",
        "diff",
        "--staged",
        "--ignore-space-change",
        "--ignore-all-space",
        "--ignore-blank-lines",
    ]
    diff_process = subprocess.run(arguments, capture_output=True, text=True)
    diff_process.check_returncode()
    return diff_process.stdout.strip()


# 1. args = parse_args()
def parse_args():
    """
    Extract the CLI arguments from argparse
    """
    parser = argparse.ArgumentParser(
        description="Generate a commit message from a diff"
    )
    parser.add_argument(
        "-r",
        "--dry-run",
        action="store_true",
        default=False,
        help="Generate a commit message and print it to the console instead of running git commit.",
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        default=False,
        help="Log debug messages",
    )
    return parser.parse_args()

args = parse_args()

async def main():


    if args.debug:
        logger.setLevel(logging.DEBUG)

    try:
        diff = get_diff()
        code_change_summaries = await summarize_changes(diff)
        commit_message = await generate_commit_message(code_change_summaries)
        commit_body = await generate_commit_body(commit_message, code_change_summaries)
    except UnicodeDecodeError:
        print("gpt-commit does not support binary files", file=sys.stderr)
        commit_message = (
            "# gpt-commit does not support binary files. "
            "Please enter a commit message manually or unstage any binary files."
        )

    if args.dry_run:
        print(commit_message)
    else:
        exit(commit(commit_message, commit_body))


if __name__ == "__main__":
    asyncio.run(main())
