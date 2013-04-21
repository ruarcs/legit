# -*- coding: utf-8 -*-

"""
legit.scm
~~~~~~~~~

This module provides the main interface to Git.
"""

import os
import sys
import subprocess
from collections import namedtuple
from exceptions import ValueError
from operator import attrgetter

from git import Repo
from git.exc import GitCommandError

from .settings import settings


LEGIT_TEMPLATE = 'Legit: stashing before {0}.'

git = os.environ.get("GIT_PYTHON_GIT_EXECUTABLE", 'git')

Branch = namedtuple('Branch', ['name', 'is_published'])


class Aborted(object):

    def __init__(self):
        self.message = None
        self.log = None


def abort(message, log=None):

    a = Aborted()
    a.message = message
    a.log = log

    settings.abort_handler(a)

def repo_check(require_remote=False):
    if repo is None:
        print 'Not a git repository.'
        sys.exit(128)

    # TODO: no remote fail
    if not repo.remotes and require_remote:
        print 'No git remotes configured. Please add one.'
        sys.exit(128)

    # TODO: You're in a merge state.



def stash_it(sync=False):
    repo_check()
    msg = 'syncing branch' if sync else 'switching branches'

    return repo.git.execute([git,
        'stash', 'save',
        LEGIT_TEMPLATE.format(msg)])


def unstash_index(sync=False):
    """Returns an unstash index if one is available."""

    repo_check()

    stash_list = repo.git.execute([git,
        'stash', 'list'])

    for stash in stash_list.splitlines():

        verb = 'syncing' if sync else 'switching'
        branch = repo.head.ref.name

        if (
            (('Legit' in stash) and
                ('On {0}:'.format(branch) in stash) and
                (verb in stash))
            or (('GitHub' in stash) and
                ('On {0}:'.format(branch) in stash) and
                (verb in stash))
        ):
            return stash[7]

def unstash_it(sync=False):
    """Unstashes changes from current branch for branch sync."""

    repo_check()

    stash_index = unstash_index(sync=sync)

    if stash_index is not None:
        return repo.git.execute([git,
            'stash', 'pop', 'stash@{{{0}}}'.format(stash_index)])


def fetch(remote):

    repo_check()

    return repo.git.execute([git, 'fetch', remote.name])


def smart_pull(remote_alias = ""):
    'git log --merges origin/master..master'

    repo_check()

    branch = repo.head.ref.name
    remote = get_remote(remote_alias)

    fetch(remote)

    return smart_merge('{0}/{1}'.format(remote.name, branch))


def smart_merge(branch, allow_rebase=True):

    repo_check()

    from_branch = repo.head.ref.name

    merges = repo.git.execute([git,
        'log', '--merges', '{0}..{1}'.format(branch, from_branch)])

    if allow_rebase:
        verb = 'merge' if merges.count('commit') else 'rebase'
    else:
        verb = 'merge'

    try:
        return repo.git.execute([git, verb, branch])
    except GitCommandError, why:
        log = repo.git.execute([git,'merge', '--abort'])
        abort('Merge failed. Reverting.', log=why)



def push(branch=None, remote_alias = ""):

    repo_check()

    remote = get_remote(remote_alias)

    if branch is None:
        return repo.git.execute([git, 'push'])
    else:
        return repo.git.execute([git, 'push', remote.name, branch])


def checkout_branch(branch):
    """Checks out given branch."""

    repo_check()

    return repo.git.execute([git, 'checkout', branch])


def sprout_branch(off_branch, branch):
    """Checks out given branch."""

    repo_check()

    return repo.git.execute([git, 'checkout', off_branch, '-b', branch])


def graft_branch(branch):
    """Merges branch into current branch, and deletes it."""

    repo_check()

    log = []

    try:
        msg = repo.git.execute([git, 'merge', '--no-ff', branch])
        log.append(msg)
    except GitCommandError, why:
        log = repo.git.execute([git,'merge', '--abort'])
        abort('Merge failed. Reverting.', log='{0}\n{1}'.format(why, log))


    out = repo.git.execute([git, 'branch', '-D', branch])
    log.append(out)
    return '\n'.join(log)


def unpublish_branch(branch):
    """Unpublishes given branch."""

    repo_check()

    return repo.git.execute([git,
        'push', remote.name, ':{0}'.format(branch)])


def publish_branch(branch):
    """Publishes given branch."""

    repo_check()

    return repo.git.execute([git,
        'push', remote.name, branch])


def get_repo():
    """Returns the current Repo, based on path."""

    work_path = subprocess.Popen([git, 'rev-parse', '--show-toplevel'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE).communicate()[0].rstrip('\n')

    if work_path:
        return Repo(work_path)
    else:
        return None

# This operation now happens on-the-fly rather than at startup.
# This gives us user the option to use any available git remotes
# rather than just the default one.
def get_remote(remote_alias):

    repo_check(require_remote=True)

    reader = repo.config_reader()

    if remote_alias.length() == 0:

        # No preferred remote was given. We will push to the default
        # upstream repo. 

        # If there is no legit section return the default remote.
        if not reader.has_section('legit'):
            return repo.remotes[0]

        # If there is no remote option in the legit section return the default.
        # With the addition of multiple repos the name for the default repo has
        # changed from "repo" to "default".
        if not any('legit' in s and 'default' in s for s in reader.sections()):
            return repo.remotes[0]

        remote_name = reader.get('legit', 'default')
        if not remote_name in [r.name for r in repo.remotes]:
            raise ValueError('Default repo has not been set! Please update your git '
                             'configuration or specify a remote. The list of '
                             'available remotes is {1}'.format(repo.remotes))

        return repo.remote(remote_name)

    else:

        # We have a name given for the remote. We must do our best to resolve this
        # and communicate with this upstream repo.

        # If there is no legit section then raise an error.
        if not reader.has_section('legit'):
            raise ValueError('No custom remotes are configured. If you wish to '
                             'push to the default repo don\'t specify a remote '
                             'name. If you wish to add a custom remote use the '
                             '"legit remote add" command.')

        # If there is no remote option in the legit section return the default.
        # With the addition of multiple repos the name for the default repo has
        # changed from "repo" to "default".
        if not any('legit' in s and remote_alias in s for s in reader.sections()):
            raise ValueError('No custom remote named {0} exists'.format(remote_alias)))

        # We now know that the "legit" section exists, and then there is an entry
        # for the given remote alias. We now need to know which git remote it specifies,
        # and if this is in fact an existing git remote.
       


def get_branches(local=True, remote_branches=True):
    """Returns a list of local and remote branches."""

    repo_check()

    # print local
    branches = []

    if remote_branches:

        # Remote refs.
        try:
            for b in remote.refs:
                name = '/'.join(b.name.split('/')[1:])

                if name not in settings.forbidden_branches:
                    branches.append(Branch(name, True))
        except (IndexError, AssertionError):
            pass

    if local:

        # Local refs.
        for b in [h.name for h in repo.heads]:

            if b not in [br.name for br in branches] or not remote_branches:
                if b not in settings.forbidden_branches:
                    branches.append(Branch(b, False))


    return sorted(branches, key=attrgetter('name'))


def get_branch_names(local=True, remote_branches=True):

    repo_check()

    branches = get_branches(local=local, remote_branches=remote_branches)

    return [b.name for b in branches]


repo = get_repo()


###################### TO DO: FOR MULTIPLE BRANCHES ######################
#
# 1.    Add a lot more error checking that we have received a remote
#       from "get_remote".
#
# 2.    Consider the way we're handling multiple remotes. Would it be a
#       lot more intuitive to just use the existing git remotes:
#
#       IF (no remotes)
#       |
#       |   Raise an exception.
#       |
#       ELSE IF (only one remote exists)
#       |
#       |   IF (no remote specified)
#       |       Assume we want to push/pull this.
#       |
#       |   ELSE IF (remote specified)
#       |       Raise an exception if user tries to give a specific remote
#       |       that isn't the existing one.
#       |
#       ELSE IF (more than one remote)
#       |
#       |   IF (no remote specified)
#       |
#       |       IF ("origin" exists)
#       |           Push/pull to this.
#       |       ELSE
#       |           Raise an exception. Tell user to specify a remote.
#       |
#       |   ELSE IF (remote specified)
#       |       
#       |       IF (this remote exists)
#       |           Push/pull to this.
#       |       ELSE
#       |           Raise an exception. Tell user to specify a valid remote.
#                   
#           
