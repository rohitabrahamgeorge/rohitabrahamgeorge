"""One command for your computer: pull, collect, push. Scheduled for Mon/Wed/Fri at 9:40 AM, before the cloud run.

  python run.py            # normal run
  python run.py --debug    # save HTML/screenshots for profiles where 0 posts were found

Steps: git pull the data branch -> refresh the roster on your machine when due (monthly) ->
collect expert posts and your own posts -> commit and push linkedin-remix/ so the cloud
routine (10:30 AM IST) picks them up.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
SKILL = os.path.dirname(HERE)
CFG = json.load(open(os.path.join(SKILL, "config.json")))
PY = sys.executable


def sh(*cmd, cwd=None, check=True):
    print("$", " ".join(cmd))
    return subprocess.run(cmd, cwd=cwd, check=check)


def main():
    root = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=SKILL, text=True).strip()
    branch = CFG["data_branch"]
    sh("git", "fetch", "origin", branch, cwd=root)
    sh("git", "checkout", branch, cwd=root)
    sh("git", "pull", "--ff-only", "origin", branch, cwd=root)
    status = subprocess.run([PY, "roster.py", "status"], cwd=os.path.join(SKILL, "scripts"),
                            capture_output=True, text=True).stdout
    print(status.strip())
    if "NEEDED" in status or "missing" in status:
        sh(PY, "collect.py", "roster", cwd=HERE)
        sh(PY, "roster.py", "verify-local", cwd=os.path.join(SKILL, "scripts"))
    sh(PY, "collect.py", "posts", *[a for a in sys.argv[1:] if a == "--debug"], cwd=HERE)
    sh("git", "add", CFG["data_dir"], os.path.join(SKILL, "config.json"), cwd=root)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=root).returncode != 0:
        sh("git", "commit", "-m", "LinkedIn remix: collected posts on local machine", cwd=root)
        sh("git", "push", "origin", f"HEAD:{branch}", cwd=root)
    print("Collected and pushed. The cloud routine takes it from here.")


if __name__ == "__main__":
    main()
