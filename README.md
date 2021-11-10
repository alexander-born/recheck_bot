# recheck_bot
bot which uses github api to recheck pull requests by adding a recheck comment.

## usage
```bash
python ~/projects/recheck_bot/recheck.py <github_username> <personal_access_token> <organization> <repo> <pr_numbers>
python ~/projects/recheck_bot/recheck.py alexanderborn 3748926347624750213754 cc-github.mywebsite.net swp/tools 42 91 34
```
#### optional arguments
```bash
--time <seconds>          # time between recheck checks in seconds (default: 600 seconds)
--recheck_on_any_failure  # rechecks on any failure (default: only on timeout)
```
