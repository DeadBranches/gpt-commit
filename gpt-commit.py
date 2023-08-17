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


# Constants
DIFF_PROMPT = (
    "Generate succinct, conscise, and high-quality summaries of the "
    "following code changes. High quality summaries remove unnecessary, "
    "redundant, or obvious details. Use clear, precise, and non-self "
    "referential language."
    "\n\nCode changes:\n"
)
COMMIT_TITLE_PROMPT = "Using the provided code change summaries, write one repository commit message in the Conventional Commits specification v1.0.0 format. The commit MUST be prefixed with a type followed by the REQUIRED terminal colon and space. Then, a description MUST immediately follow the colon and space after the type prefix. The description is a short summary of the code changes, e.g., `fix: array parsing issue when multiple spaces were contained in string`\n\nCode change summaries:\n"

COMMIT_BODY_PROMPT = "From the following commit type, description, and code change summaries, write a longer commit body according to the Conventional Commits specification v1.0.0 standard. A commit body follows the commit description and provdes additional information about the code changes. A commit body is free-form and MAY consist of any number of newline separated paragraphs. A commit body excludes the type and description."

PROMPT_CUTOFF = 10000

# Configuration file config
# API key location
CONFIG_FOLDER = "config"
CONFIG_FILENAME = "api_keys.ini"

# Fetch API keys from configuration ini file
config = configparser.ConfigParser()
script_dir = os.path.dirname(os.path.abspath(__file__))
ini_path = os.path.join(script_dir, CONFIG_FOLDER, CONFIG_FILENAME)

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
        temperature=0.3,
        messages=[
            {
                "role": "system",
                "content": "You are a senior software engineer at a software development company. Your current assignment is to perform mundane administrative tasks relating to maintaining a well-organized company github code repositories",
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

    # logging
    logger.debug("[summarize_diff()]\n  Code diff summaries:\n%s\n\n", result)

    return result


async def summarize_summaries(summaries):
    assert summaries
    result = await complete(COMMIT_TITLE_PROMPT + "\n\n" + summaries + "\n\n")

    # logging
    logger.info("[summarize_summaries()] ----------\n")
    logger.debug(
        "Commit message prompt: %s\nSummaries: %s\n\n", COMMIT_TITLE_PROMPT, summaries
    )
    logger.debug("Final completion:\n%s\n\n", result)

    return result


async def generate_commit_body(type_and_description, summaries):
    assert summaries
    result = await complete(
        f"{COMMIT_BODY_PROMPT}\n\n"
        f"Type: {type_and_description}\n"
        f"Code change summaries: {summaries}\n\n"
    )

    # logging
    logger.info("[generate_commit_body()] ----------\n")
    logger.debug(
        "Commit body prompt: %s\nFinal commit body: %s\n---------------------\n\n",
        COMMIT_BODY_PROMPT,
        result,
    )
    logger.debug("Final completion:\n%s\n\n", result)

    return result


async def summarize_changes(diff):
    if not diff:
        # no files staged or only whitespace diffs
        return "Fix whitespace"

    assembled_diffs = assemble_diffs(parse_diff(diff), PROMPT_CUTOFF)
    diff_list = [diff for diff in assembled_diffs]
    summaries = await asyncio.gather(
        *[summarize_diff(diff) for diff in assembled_diffs]
    )

    # Logging
    logger.info(
        "[summarize_changes()]\nAssembled file differences:\n%s\n\n",
        assemble_diffs,
    )
    logger.info(
        "[summarize_changes()]\nDiff list:\n%s\n\n",
        diff_list,
    )
    logger.info("[summarize_changes()]\nGathered summaries:\n%s\n\n", summaries)

    return summaries


async def generate_commit_message(summaries):
    return await summarize_summaries("\n".join(summaries))


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
        code_change_summaries = await summarize_changes(diff)
        commit_message = await generate_commit_message(code_change_summaries)
        commit_body = await generate_commit_body(commit_message, code_change_summaries)
    except UnicodeDecodeError:
        print("gpt-commit does not support binary files", file=sys.stderr)
        commit_message = (
            "# gpt-commit does not support binary files. "
            "Please enter a commit message manually or unstage any binary files."
        )

    if args.print_message:
        print(commit_message)
    else:
        exit(commit(commit_message, commit_body))


if __name__ == "__main__":
    asyncio.run(main())
