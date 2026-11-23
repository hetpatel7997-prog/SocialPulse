"""Tables that hold uploaded files, datasets and the records parsed from them.

Every record carries user_id so a query can always be limited to the owner.
`is_cleaned` separates raw rows from cleaned rows; raw rows are never deleted
by the cleaning module.
"""
from extensions import db
from models.user import TimestampMixin


class UploadedFile(TimestampMixin, db.Model):
    __tablename__ = "uploaded_files"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False, unique=True)
    extension = db.Column(db.String(10), nullable=False)
    size_bytes = db.Column(db.Integer, nullable=False)
    sha256 = db.Column(db.String(64), index=True)
    status = db.Column(db.String(20), default="uploaded", nullable=False)  # uploaded/processed/failed
    error_message = db.Column(db.Text)
    is_demo = db.Column(db.Boolean, default=False, nullable=False)

    datasets = db.relationship("Dataset", backref="file", lazy="dynamic",
                               cascade="all, delete-orphan")


class Dataset(TimestampMixin, db.Model):
    """One recognised data type found inside an uploaded file."""
    __tablename__ = "datasets"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    file_id = db.Column(db.Integer, db.ForeignKey("uploaded_files.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    kind = db.Column(db.String(30), nullable=False)  # followers/following/posts/engagement
    name = db.Column(db.String(150))
    snapshot_date = db.Column(db.DateTime)  # used for follower growth over time
    is_cleaned = db.Column(db.Boolean, default=False, nullable=False)
    # A cleaned dataset points at the raw dataset it was made from; the raw one is never changed.
    source_dataset_id = db.Column(db.Integer, db.ForeignKey("datasets.id", ondelete="SET NULL"), index=True)
    record_count = db.Column(db.Integer, default=0)
    duplicate_count = db.Column(db.Integer, default=0)
    missing_count = db.Column(db.Integer, default=0)
    invalid_count = db.Column(db.Integer, default=0)

    followers = db.relationship("Follower", backref="dataset", lazy="dynamic",
                                cascade="all, delete-orphan")
    following = db.relationship("Following", backref="dataset", lazy="dynamic",
                                cascade="all, delete-orphan")
    posts = db.relationship("Post", backref="dataset", lazy="dynamic",
                            cascade="all, delete-orphan")


class _AccountRow(TimestampMixin):
    """Shared columns for followers / following rows."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False)
    profile_url = db.Column(db.String(300))
    followed_at = db.Column(db.DateTime)


class Follower(_AccountRow, db.Model):
    __tablename__ = "followers"
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    dataset_id = db.Column(db.Integer, db.ForeignKey("datasets.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    __table_args__ = (db.UniqueConstraint("dataset_id", "username", name="uq_follower_dataset_user"),)


class Following(_AccountRow, db.Model):
    __tablename__ = "following"
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    dataset_id = db.Column(db.Integer, db.ForeignKey("datasets.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    __table_args__ = (db.UniqueConstraint("dataset_id", "username", name="uq_following_dataset_user"),)


class Post(TimestampMixin, db.Model):
    __tablename__ = "posts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    dataset_id = db.Column(db.Integer, db.ForeignKey("datasets.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    external_id = db.Column(db.String(120))  # media id / URI when the export has one
    caption = db.Column(db.Text)
    content_type = db.Column(db.String(30))  # photo / video / reel / carousel / story, only if known
    posted_at = db.Column(db.DateTime, index=True)
    likes = db.Column(db.Integer)       # NULL means "not in the export", never 0
    comments = db.Column(db.Integer)
    shares = db.Column(db.Integer)
    saves = db.Column(db.Integer)
    reach = db.Column(db.Integer)
    impressions = db.Column(db.Integer)

    metrics = db.relationship("EngagementMetric", backref="post", lazy="dynamic",
                              cascade="all, delete-orphan")
    __table_args__ = (db.Index("ix_posts_user_posted", "user_id", "posted_at"),)
