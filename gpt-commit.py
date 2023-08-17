#!/usr/bin/env python3

import argparse
import asyncio
import os
import subprocess
import sys
import configparser
import openai

import logging

import logging_utils

logger = logging.getLogger(__name__)


DIFF_PROMPT = "Generate a succinct summary of the following code changes:"
COMMIT_MSG_PROMPT = "Using no more than 45 characters, generate a descriptive commit message title complying with the Conventional Commits specification from the following summaries:"
PROMPT_CUTOFF = 10000

# Configuration file config
# API key location
config_folder = "config"
config_file = "api_keys.ini"
# OpenAI GPT3.5-turbo config ini details: "section", "key name" - > [section]\n"key name" = 000000000000
# openai_key = ("openai", "gpt35")

# Fetch API keys from configuration ini file
config = configparser.ConfigParser()
script_dir = os.path.dirname(os.path.abspath(__file__))
ini_path = os.path.join(script_dir, config_folder, config_file)
# api_keys=os.path.join(os.path.abspath(config_folder), config_file)
print(ini_path)
config.read(ini_path)
openai_gpt35key = config.get("openai", "gpt35")

openai.api_key = openai_gpt35key


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
    completion_resp = await openai.ChatCompletion.acreate(
        model="gpt-3.5-turbo",
        messages=[
            {
                "role": "system",
                "content": "You are staff at a software development company assigned to mundane code repository administrative tasks.",
            },
            {"role": "user", "content": prompt[: PROMPT_CUTOFF + 100]},
        ],
        max_tokens=128,
    )
    completion = completion_resp.choices[0].message.content.strip()
    return completion


async def summarize_diff(diff):
    assert diff
    result = await complete(DIFF_PROMPT + "\n\n" + diff + "\n\n")
    logger.debug("[summarize_diff()]\nDiff summary:\n%s\n\n", result)

    return result


async def summarize_summaries(summaries):
    assert summaries
    logger.info("[summarize_summaries()] ----------\n")
    logger.debug(
        "Commit message prompt: %s\nSummaries: %s\n\n", COMMIT_MSG_PROMPT, summaries
    )
    result = await complete(COMMIT_MSG_PROMPT + "\n\n" + summaries + "\n\n")
    logger.debug("Final completion:\n%s\n\n", result)

    return result


async def summarize_changes(diff):
    if not diff:
        # no files staged or only whitespace diffs
        return "Fix whitespace"

    assembled_diffs = assemble_diffs(parse_diff(diff), PROMPT_CUTOFF)
    logger.info(
        "[generate_commit_message()]\nAssembled file differences:\n%s\n\n",
        assemble_diffs,
    )
    summaries = await asyncio.gather(
        *[summarize_diff(diff) for diff in assembled_diffs]
    )
    logger.info("[generate_commit_message()]\nGathered summaries:\n%s\n\n", summaries)

    return summaries


async def generate_commit_message(summaries):
    return await summarize_summaries("\n".join(summaries))


def commit(message, changes):
    # will ignore message if diff is empty
    commit_command = ["git", "commit", "--edit", "--message", message]

    for change in changes:
        commit_command.append("--message")
        commit_command.append(change)

    return subprocess.run(commit_command).returncode


def parse_args():
    """
    Extract the CLI arguments from argparse
    """
    parser = argparse.ArgumentParser(
        description="Generate a commit message from a diff"
    )

    parser.add_argument(
        "-p",
        "--print-message",
        action="store_true",
        default=False,
        help="Print message in place of performing commit",
    )

    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        default=False,
        help="Log debug messages",
    )

    return parser.parse_args()


async def main():
    args = parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    try:
        diff = get_diff()
        change_summaries = await summarize_changes(diff)
        commit_message = await generate_commit_message(change_summaries)
    except UnicodeDecodeError:
        print("gpt-commit does not support binary files", file=sys.stderr)
        commit_message = (
            "# gpt-commit does not support binary files. "
            "Please enter a commit message manually or unstage any binary files."
        )

    if args.print_message:
        print(commit_message)
    else:
        exit(commit(commit_message, change_summaries))


if __name__ == "__main__":
    asyncio.run(main())
