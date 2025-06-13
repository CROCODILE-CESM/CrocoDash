import os
import git

def git_commit_snapshot(snapshot_path, msg, repo_root):
    repo = git.Repo(repo_root)
    rel_path = os.path.relpath(snapshot_path, repo_root)
    if os.path.exists(snapshot_path):
        snapshots_dir = os.path.dirname(snapshot_path)
        rel_snapshots_dir = os.path.relpath(snapshots_dir, repo_root)
        repo.git.add(rel_snapshots_dir)
        if repo.is_dirty(untracked_files=True):
            repo.index.commit(msg)
            return f"Committed snapshot '{os.path.basename(snapshot_path)}' to Git: {msg}"
        else:
            return "Nothing to commit."
    else:
        if rel_path in repo.git.ls_files().splitlines():
            repo.git.rm(rel_path)
            if repo.is_dirty(untracked_files=True):
                repo.index.commit(msg)
                return f"Committed deletion of snapshot '{os.path.basename(snapshot_path)}' to Git: {msg}"
            else:
                return "Nothing to commit."
        else:
            return f"Snapshot file '{snapshot_path}' does not exist and is not tracked by git."

def git_create_branch_and_switch(branch, repo_root):
    repo = git.Repo(repo_root)
    repo.git.checkout('-b', branch)
    return repo.active_branch.name

def git_delete_branch_and_switch(branch, repo_root):
    repo = git.Repo(repo_root)
    if repo.active_branch.name == branch:
        raise Exception("Cannot delete the currently checked out branch. Please checkout another branch first.")
    repo.git.branch('-D', branch)
    return repo.active_branch.name

def git_checkout_branch(branch, repo_root):
    repo = git.Repo(repo_root)
    repo.git.checkout(branch)
    return repo.active_branch.name

def git_list_branches(repo_root):
    repo = git.Repo(repo_root)
    return [head.name for head in repo.heads]