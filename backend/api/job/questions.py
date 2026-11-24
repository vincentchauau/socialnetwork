"""The comments on a job (`sn_shared.comments`): questions and answers beside the description, for anybody who can see the job; its
owner may delete what others said."""

from sn_shared import comments

from api.job.access import get_visible_job_description

JOB_COMMENTS = comments.CommentKind(
    "job", "/jobs/{object_id}/comments", "/comments/{comment_id}",
    visible=lambda db, job_id, user: get_visible_job_description(db, job_id, user), content_min=1, content_max=1000,
    moderator=lambda job, user: job.owner_id == user.user_id, tag="comments",
)
router = comments.comments_router(JOB_COMMENTS)
