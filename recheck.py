import argparse
import subprocess
import time
import json


def ParseArguments():
    parser = argparse.ArgumentParser(
        prog="recheck bot for github", description="rechecks pull request"
    )
    parser.add_argument("user", type=str, help="github username")
    parser.add_argument("token", type=str, help="personal access token")
    parser.add_argument("org", type=str, help="github organization")
    parser.add_argument("repo", type=str, help="git repo")
    parser.add_argument("prs", type=str, help="pr number list", nargs="+")
    parser.add_argument(
        "--time", type=int, default=600, help="time between recheck checks in seconds"
    )
    parser.add_argument(
        "--recheck_on_any_failure",
        action="store_true",
        help="rechecks on any failure (default: only on timeout)",
    )
    return parser.parse_args()


def shell(command):
    subprocess.call(command, shell=True, stdout=subprocess.DEVNULL)


def convert_bytes_to_list_of_strings(bytestring):
    return bytestring.decode("utf-8")


def shell_output(command):
    try:
        return convert_bytes_to_list_of_strings(
            subprocess.check_output(command, shell=True)
        )
    except:
        return ""


class GitHubApi:
    def __init__(self, user, token, org):
        self.user = user
        self.token = token
        self.org = org

    def _get(self, call, args):
        return json.loads(
            shell_output(
                f"curl -s {args} -u {self.user}:{self.token} https://{self.org}/api/v3/{call}"
            )
        )

    def get(self, call):
        return self._get(call, "")

    def dev_get(self, call):
        return self._get(
            call, '-H "Accept: application/vnd.github.antiope-preview+json"'
        )

    def post(self, call):
        shell(
            f"curl -s -X POST -u {self.user}:{self.token} https://{self.org}/api/v3/{call}"
        )


class PrRechecker:
    def __init__(self, github, repo, pr, recheck_on_any_failure):
        self.github = github
        self.repo = repo
        self.pr = pr
        self.pr_info = self.github.get(f"repos/{self.repo}/pulls/{self.pr}")
        self.recheck_on_any_failure = recheck_on_any_failure

    def check_failed(self, run):
        completed = run["status"] == "completed"
        failed = run["conclusion"] == "failure"
        return completed and failed

    def check_timed_out(self, run):
        return "TIMED_OUT" in run["output"]["summary"]

    def get_last_commit(self):
        return self.pr_info["head"]["sha"]

    def commit_status_success(self, commit_sha):
        commit_status = github.get(f"repos/{self.repo}/commits/{commit_sha}/status")
        return commit_status["state"] == "success"

    def any_check_job_failed(self):
        commit_sha = self.get_last_commit()
        if not self.commit_status_success(commit_sha):
            return False

        check_runs = self.github.dev_get(
            f"repos/{self.repo}/commits/{commit_sha}/check-runs"
        )
        for run in check_runs["check_runs"]:
            if self.check_failed(run) and (
                self.check_timed_out(run) or self.recheck_on_any_failure
            ):
                return True
        return False

    def last_comment_is_recheck(self):
        page = 1
        last_comment = ""
        while True:
            comments = self.github.get(
                f"repos/{self.repo}/issues/{self.pr}/comments?page={page}"
            )
            page += 1
            if not comments:
                break
            last_comment = comments[-1]["body"]
        return last_comment == "recheck"

    def has_merge_conflicts(self):
        return self.pr_info["mergeable_state"] == "dirty"

    def needs_recheck(self):
        return (
            not self.last_comment_is_recheck()
            and not self.has_merge_conflicts()
            and self.any_check_job_failed()
        )

    def comment(self, text):
        self.github.post(
            f"""repos/{self.repo}/issues/{self.pr}/comments -d '{{"body":"{text}"}}'"""
        )


if __name__ == "__main__":
    args = ParseArguments()
    github = GitHubApi(args.user, args.token, args.org)
    while True:
        for pr in args.prs:
            pr_rechecker = PrRechecker(
                github, args.repo, pr, args.recheck_on_any_failure
            )
            if pr_rechecker.has_merge_conflicts():
                print(f"[WARNING]: {args.repo}#{pr} has merge conflicts")
                continue
            if pr_rechecker.needs_recheck():
                print(f"[INFO]: {args.repo}#{pr} rechecking")
                pr_rechecker.comment("recheck")
            else:
                print(f"[INFO]: {args.repo}#{pr} no recheck necessary")
        time.sleep(args.time)
