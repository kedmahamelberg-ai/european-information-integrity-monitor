"""Wait until GitHub's artifact API can see the Pages upload before deploy."""
import json
import os
import time
import urllib.error
import urllib.request


def wait_for_artifact(repository, run_id, token, *, attempts=12, pause=5, opener=urllib.request.urlopen, sleep=time.sleep):
    url=f"https://api.github.com/repos/{repository}/actions/runs/{run_id}/artifacts?name=github-pages&per_page=100"
    request=urllib.request.Request(url,headers={"Authorization":f"Bearer {token}","Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"})
    for attempt in range(attempts):
        try:
            with opener(request,timeout=10) as response:
                artifacts=json.load(response).get("artifacts",[])
            matches=sum(artifact.get("name")=="github-pages" for artifact in artifacts)
            if matches==1:
                print("Pages artifact is visible to the deployment API",flush=True)
                return
            if matches>1:
                raise RuntimeError("Multiple Pages artifacts found in this run")
        except urllib.error.HTTPError as error:
            if error.code not in {404,429,502,503,504}:
                raise RuntimeError(f"Artifact visibility check failed: HTTP {error.code}") from None
        except urllib.error.URLError:
            pass
        if attempt<attempts-1:
            sleep(pause)
    raise RuntimeError("Pages artifact was not visible to the deployment API within the retry window")


if __name__=="__main__":
    wait_for_artifact(os.environ["GITHUB_REPOSITORY"],os.environ["GITHUB_RUN_ID"],os.environ["GITHUB_TOKEN"])
