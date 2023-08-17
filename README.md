# gpt-commit fork

This is [markuswt/gpt-commit](https://github.com/markuswt/gpt-commit) with some modifications to add a few features.

Changes made:
- Text completion uses the OpenAI chat completion API with the gpt-3.5-turbo model instead of the text-divinci-003 model.
- [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/#specification) formatted commit messages.
- Commit details include individual summaries for each code change.

# gpt-commit 

Generate commit messages using GPT-3.5-turbo. To use `gpt-commit`, simply invoke it whenever you'd use `git commit`. Git will prompt you to edit the generated commit message.

```
git add .
./gpt-commit.py
```

## Getting Started

Install `openai` and clone `gpt-commit`.

```
pip install openai
git clone git@github.com:DeadBranches/gpt-commit.git
```

Rename `./config/api_keys.ini.example` to `./config/api_keys.ini`

In `api_keys.ini` replace `sk-111111` with your [OpenAI API key](https://platform.openai.com/account/api-keys)


## Using `gpt-commit`

You could set up git to automatically invoke `gpt-commit,` or you could call `gpt-commit` manually.

### Modify `git commit` (optional)

If you want `git commit` to automatically invoke `gpt-commit`, copy `gpt-commit.py` and `prepare-commit-msg` to the `.git/hooks` directory in any project where you want to modify `git commit`.

### Modify `.bashrc` (optional)

Modify `script_path` then append the following bash excerpt to your .bashrc or .bash_profile file

```
gpt-commit () {
    (  
        script_path="/full/path/to/gpt-commit/gpt-commit.py"

        # Store any arguments in a variable
        args="$@"

        # Run the Python script with the provided arguments
        python "$script_path" $args

        # Unset the arguments variable
        unset args
    )
}
```

Use `gpt-commit` by invoking the `gpt-commit` command as part of your usual git commit process. For example,

```
git add .
gpt-commit
git push
```
