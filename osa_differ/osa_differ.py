#!/usr/bin/env python
# Copyright 2016, Major Hayden
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Analyzes the differences between two OpenStack-Ansible commits."""
import argparse
import json
import logging
import os
import sys


from git import Repo
import jinja2
import requests
import yaml


def create_parser():
    """Setup argument Parsing."""
    description = """OpenStack-Ansible Release Diff Generator
----------------------------------------

Finds changes in OpenStack projects and OpenStack-Ansible roles between two
commits in OpenStack-Ansible.

"""

    parser = argparse.ArgumentParser(
        usage='%(prog)s',
        description=description,
        epilog='Licensed "Apache 2.0"',
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        'old_commit',
        action='store',
        nargs=1,
        help="Git SHA of the older commit",
    )
    parser.add_argument(
        'new_commit',
        action='store',
        nargs=1,
        help="Git SHA of the newer commit",
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        default=False,
        help="Enable debug output",
    )
    parser.add_argument(
        '-d', '--directory',
        action='store',
        default="~/.osa-differ",
        help="Git repo storage directory (default: ~/.osa-differ)",
    )
    parser.add_argument(
        '-u', '--update',
        action='store_true',
        default=False,
        help="Fetch latest changes to repo",
    )
    display_opts = parser.add_argument_group("Limit scope")
    display_opts.add_argument(
        "--skip-projects",
        action="store_true",
        help="Skip checking for changes in OpenStack projects"
    )
    display_opts.add_argument(
        "--skip-roles",
        action="store_true",
        help="Skip checking for changes in OpenStack-Ansible roles"
    )
    output_desc = ("Note: Output is always printed to stdout unless "
                   "--quiet is provided.")
    output_opts = parser.add_argument_group('Output options', output_desc)
    output_opts.add_argument(
        '--quiet',
        action='store_true',
        default=False,
        help="Do not output to stdout",
    )
    output_opts.add_argument(
        '--gist',
        action='store_true',
        default=False,
        help="Output into a GitHub Gist",
    )
    output_opts.add_argument(
        '--file',
        metavar="FILENAME",
        action='store',
        help="Output to a file",
    )
    return parser


def get_commits(repo_dir, old_commit, new_commit, hide_merges=True):
    """Find all commits between two commit SHAs."""
    repo = Repo(repo_dir)
    commits = repo.iter_commits(rev="{0}..{1}".format(old_commit, new_commit))
    if hide_merges:
        return [x for x in commits if not x.summary.startswith("Merge ")]
    else:
        return list(commits)


def get_commit_url(repo_url):
    """Determine URL to view commits for repo."""
    if "github.com" in repo_url:
        return repo_url
    if "git.openstack.org" in repo_url:
        uri = '/'.join(repo_url.split('/')[-2:])
        return "https://github.com/{0}".format(uri)

    # If it didn't match these conditions, just return it.
    return repo_url


def get_logger(debug=False):
    """Set up the logger."""
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    logging.basicConfig(level=logging.WARNING, format=log_format)
    logger = logging.getLogger(__name__)

    if debug:
        logger.setLevel(logging.DEBUG)

    return logger


def get_projects(osa_repo_dir, yaml_files, commit):
    """Get all projects from multiple YAML files."""
    yaml_parsed = []
    for yaml_file in yaml_files:
        # Check out the correct commit SHA from the repository
        repo = Repo(osa_repo_dir)
        repo.head.reference = repo.commit(commit)
        repo.head.reset(index=True, working_tree=True)

        filename = "{0}/{1}".format(osa_repo_dir, yaml_file)
        with open(filename, 'r') as f:
            yaml_parsed.append(yaml.load(f))

    merged_dicts = {k: v for d in yaml_parsed for k, v in d.items()}

    return merged_dicts


def get_roles(osa_repo_dir, commit):
    """Read OSA role information at a particular commit."""
    repo = Repo(osa_repo_dir)
    repo.head.reference = repo.commit(commit)
    repo.head.reset(index=True, working_tree=True)

    filename = "{0}/ansible-role-requirements.yml".format(osa_repo_dir)
    with open(filename, 'r') as f:
        roles_yaml = yaml.load(f)

    return roles_yaml


def parse_arguments():
    """Parse arguments."""
    parser = create_parser()
    args = parser.parse_args()
    return args


def post_gist(report_data, old_sha, new_sha):
    """Post the report to a GitHub Gist and return the URL of the gist."""
    payload = {
        "description": ("Changes in OpenStack-Ansible between "
                        "{0} and {1}".format(old_sha, new_sha)),
        "public": True,
        "files": {
            "osa-diff-{0}-{1}.rst".format(old_sha, new_sha): {
                "content": report_data
            }
        }
    }
    url = "https://api.github.com/gists"
    r = requests.post(url, data=json.dumps(payload))
    response = r.json()
    return response['html_url']


def prepare_storage_dir(storage_directory):
    """Prepare the storage directory."""
    storage_directory = os.path.expanduser(storage_directory)
    if not os.path.exists(storage_directory):
        os.mkdir(storage_directory)

    return storage_directory


def render_template(template_file, template_vars):
    """Render a jinja template."""
    # Load our Jinja templates
    template_dir = "{0}/templates".format(
        os.path.dirname(os.path.abspath(__file__))
    )
    jinja_env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(template_dir),
        trim_blocks=True
    )
    rendered = jinja_env.get_template(template_file).render(template_vars)

    return rendered


def repo_clone(repo_dir, repo_url):
    """Clone repository to this host."""
    repo = Repo.clone_from(repo_url, repo_dir)
    return repo


def repo_pull(repo_dir, repo_url, fetch=False):
    """Reset repository and optionally update it."""
    # Make sure the repository is reset to the master branch.
    repo = Repo(repo_dir)
    repo.heads.master.checkout()
    repo.head.reset(index=True, working_tree=True)

    # Only get the latest updates if requested.
    if fetch:
        repo.remotes['origin'].pull()

    return repo


def update_repo(repo_dir, repo_url, fetch=False):
    """Clone the repo if it doesn't exist already, otherwise update it."""
    repo_exists = os.path.exists(repo_dir)
    if repo_exists:
        repo = repo_pull(repo_dir, repo_url, fetch)
    else:
        repo = repo_clone(repo_dir, repo_url)

    return repo


def validate_commits(repo_dir, commits):
    """Test if a commit is valid for the repository."""
    repo = Repo(repo_dir)
    for commit in commits:
        try:
            commit = repo.commit(commit)
        except:
            raise Exception("Commit {0} could not be found".format(commit))

    return True


def validate_commit_range(repo_dir, old_commit, new_commit):
    """Check if commit range is valid. Flip it if needed."""
    # Are there any commits between the two commits that were provided?
    commits = get_commits(repo_dir, old_commit, new_commit)
    if len(commits) == 0:
        # The user might have gotten their commits out of order. Let's flip
        # the order of the commits and try again.
        commits = get_commits(repo_dir, new_commit, old_commit)
        if len(commits) == 0:
            # Okay, so there really are no commits between the two commits
            # provided by the user. :)
            msg = "The commit range provided is invalid."
            raise Exception(msg)
        else:
            return 'flip'

    return True


def run_osa_differ():
    """The script starts here."""
    # Get our arguments from the command line
    args = parse_arguments()

    # Configure logging
    logger = get_logger(args.debug)

    # Create the storage directory if it doesn't exist already.
    try:
        storage_directory = prepare_storage_dir(args.directory)
    except OSError:
        print("ERROR: Couldn't create the storage directory {0}. "
              "Please create it manually.".format(args.directory))
        sys.exit(1)

    # Prepare the main OpenStack-Ansible repository
    osa_old_commit = args.old_commit[0]
    osa_new_commit = args.new_commit[0]
    osa_repo_url = "https://git.openstack.org/openstack/openstack-ansible"
    osa_repo_dir = "{0}/openstack-ansible".format(storage_directory)
    update_repo(osa_repo_dir, osa_repo_url)

    # Are these commits valid?
    validate_commits(osa_repo_dir, [osa_old_commit, osa_new_commit])

    # Do we have a valid commit range?
    validate_commit_range(osa_repo_dir, osa_old_commit, osa_new_commit)

    # Get the commits in the range
    commits = get_commits(osa_repo_dir, osa_old_commit, osa_new_commit)

    # Start off our report with a header and our OpenStack-Ansible commits.
    template_vars = {
        'args': args,
        'repo': 'openstack-ansible',
        'commits': commits,
        'commit_base_url': get_commit_url(osa_repo_url),
        'old_sha': osa_old_commit,
        'new_sha': osa_new_commit
    }
    report = render_template('offline-header.j2', template_vars)

    # Get the list of OpenStack roles from the newer and older commits.
    role_yaml = get_roles(osa_repo_dir, osa_old_commit)
    role_yaml_latest = get_roles(osa_repo_dir, osa_new_commit)

    # Don't loop through the roles if the user asked us not to do so.
    if args.skip_roles:
        role_yaml_latest = []
    else:
        report += ("OpenStack-Ansible Roles\n"
                   "-----------------------")

    for role in role_yaml_latest:
        # Prepare our repo directory and clone the repo if needed. Only pull
        # if the user requests it.
        repo_dir = "{0}/{1}".format(storage_directory, role['name'])
        repo_url = role['src']
        update_repo(repo_dir, repo_url, args.update)

        # Get the commit SHAs for this role from the older and newer
        # OpenStack-Ansible commits.
        role_old_sha = next(x['version'] for x in role_yaml
                            if x['name'] == role['name'])
        role_new_sha = role['version']

        # Loop through the commits and render our template.
        commits = get_commits(repo_dir, role_old_sha, role_new_sha)
        template_vars = {
            'repo': role['name'],
            'commits': commits,
            'commit_base_url': get_commit_url(repo_url),
            'old_sha': role_old_sha,
            'new_sha': role_new_sha
        }
        rst = render_template('offline-repo-changes.j2', template_vars)
        report += rst

    # Get the list of OpenStack projects from newer commit and older commit.
    yaml_files = [
        'playbooks/defaults/repo_packages/openstack_services.yml',
        'playbooks/defaults/repo_packages/openstack_other.yml'
    ]
    project_yaml = get_projects(osa_repo_dir, yaml_files, osa_old_commit)
    project_yaml_latest = get_projects(osa_repo_dir, yaml_files,
                                       osa_new_commit)

    # Narrow down a list of projects from the latest YAML we retrieved.
    projects = sorted([x[:-9] for x in project_yaml_latest.keys()
                      if x.endswith('git_repo')])

    # Don't loop through the projects if the user asked us not to do so.
    if args.skip_projects:
        project_yaml_latest = []
    else:
        report += ("OpenStack Projects\n"
                   "------------------")

    # Loop through each project and find changes. If we've been asked to update
    # the repository, let's do that too.
    logger.info("Looping through projects to check for changes")
    for project in projects:
        # Prepare our repo directory and clone the repo if needed. Only pull
        # if the user requests it.
        repo_dir = "{0}/{1}".format(storage_directory, project)
        repo_url = project_yaml_latest['{0}_git_repo'.format(project)]
        update_repo(repo_dir, repo_url, args.update)

        # Get the commit SHAs for this project from the older and newer
        # OpenStack-Ansible commits.
        key_for_sha = "{0}_git_install_branch".format(project)
        project_new_sha = project_yaml_latest[key_for_sha]

        # There's a chance that this project was recently added and it might
        # not have existed in the YAML files in the previous OSA release. If
        # that happens, let's just skip it.
        try:
            project_old_sha = project_yaml[key_for_sha]
        except KeyError:
            continue

        # Loop through the commits and render our template.
        commits = get_commits(repo_dir, project_old_sha, project_new_sha)
        template_vars = {
            'repo': project,
            'commits': commits,
            'commit_base_url': get_commit_url(repo_url),
            'old_sha': project_old_sha,
            'new_sha': project_new_sha
        }
        rst = render_template('offline-repo-changes.j2', template_vars)
        report += rst

    # Print the report to stdout unless the user specified --quiet.
    if not args.quiet:
        print(report)

    if args.gist:
        gist_url = post_gist(report, osa_old_commit, osa_new_commit)
        print("Report posted to GitHub Gist: {0}".format(gist_url))

    if args.file is not None:
        print("Report written to file: {0}".format(args.file))
        with open(args.file, 'w') as f:
            f.write(report)

if __name__ == "__main__":
    run_osa_differ()
