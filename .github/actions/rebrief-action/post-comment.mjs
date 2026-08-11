const fs = require("fs");

const MARKER = "<!-- rebrief-ci-report -->";

function readCommentBody() {
  const commentPath = process.env.COMMENT_BODY_PATH;
  if (!commentPath) {
    throw new Error("COMMENT_BODY_PATH is not set.");
  }

  return fs.readFileSync(commentPath, "utf8");
}

async function findExistingComment(issueNumber) {
  const { owner, repo } = context.repo;
  let page = 1;

  while (true) {
    const { data: comments } = await github.rest.issues.listComments({
      owner,
      repo,
      issue_number: issueNumber,
      per_page: 100,
      page,
    });

    const existing = comments.find((comment) => comment.body?.includes(MARKER));
    if (existing) {
      return existing;
    }

    if (comments.length < 100) {
      return null;
    }

    page += 1;
  }
}

module.exports = async ({ core, github, context }) => {
  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    throw new Error(
      "github-token is required when post-comment is true. " +
        "Pass secrets.GITHUB_TOKEN and grant pull-requests: write permission."
    );
  }

  const pullRequest = context.payload.pull_request;
  if (!pullRequest) {
    core.info("Not a pull_request event; skipping comment post.");
    return;
  }

  const body = readCommentBody();
  if (!body.trim()) {
    throw new Error("Comment body is empty; refusing to post.");
  }

  const { owner, repo } = context.repo;
  const issueNumber = pullRequest.number;
  const existing = await findExistingComment(issueNumber);

  if (existing) {
    await github.rest.issues.updateComment({
      owner,
      repo,
      comment_id: existing.id,
      body,
    });
    core.info(`Updated existing rebrief comment (id=${existing.id}).`);
    return;
  }

  await github.rest.issues.createComment({
    owner,
    repo,
    issue_number: issueNumber,
    body,
  });
  core.info("Created new rebrief comment.");
};
