from extensions import db
from models.user import TimestampMixin


class EngagementMetric(TimestampMixin, db.Model):
    """Computed per-post engagement numbers (kept separate from raw post data)."""
    __tablename__ = "engagement_metrics"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    total_interactions = db.Column(db.Integer)
    engagement_rate = db.Column(db.Float)  # NULL unless follower/reach data exists
    is_outlier = db.Column(db.Boolean, default=False)
    performance_tier = db.Column(db.String(20))  # high / average / low


class AnalyticsResult(TimestampMixin, db.Model):
    """Stored output of analyses (insights, ML results) as JSON."""
    __tablename__ = "analytics_results"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    dataset_id = db.Column(db.Integer, db.ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    result_type = db.Column(db.String(40), nullable=False)  # insights / kmeans / anomalies / forecast
    payload = db.Column(db.JSON, nullable=False)


class Report(TimestampMixin, db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    report_type = db.Column(db.String(10), nullable=False)  # pdf / xlsx
    file_name = db.Column(db.String(255), nullable=False, unique=True)
    size_bytes = db.Column(db.Integer)
