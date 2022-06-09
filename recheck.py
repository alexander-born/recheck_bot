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
    def __init__(
        self, github: GitHubApi, repo: str, pr: str, recheck_on_any_failure: bool
    ):
        self.github = github
        self.repo = repo
        self.pr = pr
        self.recheck_on_any_failure = recheck_on_any_failure
        self.pr_info = self.github.get(f"repos/{self.repo}/pulls/{self.pr}")
        self.check_runs = self.github.dev_get(
            f"repos/{self.repo}/commits/{self.get_last_commit()}/check-runs"
        )
        self.last_comment = self.get_last_comment()

    def conclusion(self, run, conclusion):
        completed = run["status"] == "completed"
        failed = run["conclusion"] == conclusion
        return completed and failed

    def failed(self, run):
        return self.conclusion(run, "failure")

    def successfull(self, run):
        return self.conclusion(run, "success")

    def timed_out(self, run):
        summary = run["output"]["summary"]
        return "TIMED_OUT" in summary or "RETRY_LIMIT" in summary

    def get_last_commit(self):
        return self.pr_info["head"]["sha"]

    def commit_status_success(self):
        commit_status = github.get(
            f"repos/{self.repo}/commits/{self.get_last_commit()}/status"
        )
        return commit_status["state"] == "success"

    def name(self, name, run):
        return name in run["external_id"]

    def run_successfull(self, name):
        if not self.commit_status_success():
            return False

        for run in self.check_runs["check_runs"]:
            if self.name(name, run) and self.successfull(run):
                return True
        return False

    def run_failed(self, name):
        if not self.commit_status_success():
            return False

        for run in self.check_runs["check_runs"]:
            if (
                self.failed(run)
                and self.name(name, run)
                and (self.timed_out(run) or self.recheck_on_any_failure)
            ):
                return True
        return False

    def get_last_comment(self):
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
        return last_comment

    def last_comment_is(self, comment):
        return self.last_comment == comment

    def has_merge_conflicts(self):
        return self.pr_info["mergeable_state"] == "dirty"

    def needs_recheck(self):
        return not self.last_comment_is("recheck") and self.run_failed("check")

    def needs_regate(self):
        return (
            not self.last_comment_is("regate")
            and self.run_failed("gate")
            and (
                self.run_successfull("check") or self.run_successfull("priority-check")
            )
        )

    def comment(self, text):
        self.github.post(
            f"""repos/{self.repo}/issues/{self.pr}/comments -d '{{"body":"{text}"}}'"""
        )
        print(f"[INFO]: {self.repo}#{self.pr} {text}")


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
            elif pr_rechecker.needs_recheck():
                pr_rechecker.comment("recheck")
            elif pr_rechecker.needs_regate():
                pr_rechecker.comment("regate")
            else:
                print(f"[INFO]: {args.repo}#{pr} no recheck/gate necessary")
        time.sleep(args.time)
