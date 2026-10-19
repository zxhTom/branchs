"""Per-command Git network settings; never mutate the user's Git config."""

import os
from contextlib import contextmanager

@contextmanager
def git_network(repo):
    """Run Git network commands without environment or configured HTTP proxies."""
    # Git's remote-specific proxy setting has higher priority than http.proxy.
    # Command-scope values override system/global/repository configuration.
    keys = ["http.proxy"] + [f"remote.{r.name}.proxy" for r in repo.remotes]
    existing_count = int(os.environ.get("GIT_CONFIG_COUNT", "0"))
    env = {
        "HTTP_PROXY": "", "HTTPS_PROXY": "", "ALL_PROXY": "",
        "http_proxy": "", "https_proxy": "", "all_proxy": "",
        "NO_PROXY": "*", "no_proxy": "*",
        "GIT_CONFIG_COUNT": str(existing_count + len(keys)),
    }
    for offset, key in enumerate(keys, existing_count):
        env[f"GIT_CONFIG_KEY_{offset}"] = key
        env[f"GIT_CONFIG_VALUE_{offset}"] = ""
    with repo.git.custom_environment(**env):
        yield
