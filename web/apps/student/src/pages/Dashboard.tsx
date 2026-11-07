import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getData, mode } from "../lib/data";
import { demoLink } from "../lib/demo";
import { resumeDestination } from "../lib/navigation";
import { PageState } from "../components/PageState";
import { reviewLink, usePendingReviews } from "../lib/reviews";
import type { DashboardData, PlanData, RevisionData } from "../lib/contracts";
export function Dashboard() {
  const query = useQuery({
    queryKey: ["dashboard", mode()],
    queryFn: () => getData<DashboardData>("/api/v1/dashboard"),
  });
  const plan = useQuery({ queryKey: ["study-plan", mode()], queryFn: () => getData<PlanData>("/api/v1/plan") });
  const revision = useQuery({
    queryKey: ["revision-due", mode()],
    queryFn: () => getData<RevisionData>("/api/v1/revision/due"),
  });
  const reviews = usePendingReviews().data;
  const data = query.data;
  const resume = resumeDestination();
  const awaiting = data?.context && data.context.readiness !== "ready";
  return (
    <div className="space-y-5">
      <h1 className="page-title">Today</h1>
      <PageState
        loading={query.isPending}
        refreshing={query.isFetching && Boolean(data)}
        error={query.error}
        retry={() => query.refetch()}
      />
      {awaiting && (
        <p className="card">
          The syllabus for this attempt is awaiting review.{" "}
          <Link className="topic-link" to={demoLink("/syllabus?preview=draft")}>
            Preview draft syllabus
          </Link>{" "}
          ·{" "}
          <Link className="topic-link" to={demoLink("/progress?tab=coverage")}>
            View readiness
          </Link>
        </p>
      )}
      {reviews && reviews.count > 0 && (
        <section className="card attention space-y-3" aria-labelledby="pending-reviews-heading">
          <h2 id="pending-reviews-heading">Waiting for your review</h2>
          <p>
            {reviews.count === 1
              ? "Another student changed a syllabus descriptor."
              : `Other students changed ${reviews.count} syllabus descriptors.`}{" "}
            Classification uses a change only after a second reviewer approves it.
          </p>
          {reviews.items.slice(0, 5).map((item) => (
            <div className="study-row" key={`${item.version_id}:${item.node_id}`}>
              <h3>{item.name}</h3>
              <p className="study-meta">
                {item.paper_code} · Revision {item.revision} · Changed{" "}
                {new Date(item.changed_at).toLocaleDateString(undefined, {
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                })}
              </p>
              <a className="topic-link" href={reviewLink(item)}>
                Review change
              </a>
            </div>
          ))}
        </section>
      )}
      {data && (
        <>
          <div className="study-stack">
            <section className="continue-band">
              <h2>Continue studying</h2>
              {resume ? (
                <>
                  <h3 className="continue-title">{resume.title}</h3>
                  <p className="study-meta">
                    {resume.paper} · {resume.breadcrumb}
                  </p>
                  <Link className="primary-action inline-flex" to={demoLink(resume.path)}>
                    Continue
                  </Link>
                  <p className="study-meta">
                    Device-local navigation. Opening content does not record study time or completion.
                  </p>
                </>
              ) : (
                <>
                  <p>Choose a topic to begin. Your last topic or question on this device will appear here.</p>
                  <Link className="primary-action inline-flex" to={demoLink("/syllabus")}>
                    Start with your syllabus
                  </Link>
                </>
              )}
            </section>
            <div className="study-columns">
              <section className="ledger-section">
                <h2>Next in your plan</h2>
                <PageState loading={plan.isPending} error={plan.error} retry={() => plan.refetch()} />
                {plan.data && (
                  <>
                    <p className="study-meta">
                      {plan.data.basis === "syllabus"
                        ? "Syllabus-based"
                        : plan.data.basis === "scored"
                          ? "Historically ranked"
                          : "Plan basis unavailable"}
                    </p>
                    {plan.data.items.slice(0, 3).map((item) => (
                      <div className="study-row" key={item.node_id}>
                        <h3>{item.node_name}</h3>
                        <p className="study-meta">
                          {item.paper_code} · {plan.data.minutes_per_subtopic} minutes
                        </p>
                        <p>{item.reason}</p>
                        <Link
                          className="topic-link"
                          to={demoLink(
                            `/syllabus?${new URLSearchParams({ paper: item.paper_id, node: item.node_id })}`,
                          )}
                        >
                          Open topic
                        </Link>
                      </div>
                    ))}
                    {!plan.data.items.length && <p>No topics are allocated for your current selection.</p>}
                    <Link className="topic-link" to={demoLink("/plan")}>
                      View your study plan
                    </Link>
                  </>
                )}
              </section>
              <aside className="study-stack">
                <section className="ledger-section">
                  <h2>Revision due</h2>
                  <PageState loading={revision.isPending} error={revision.error} retry={() => revision.refetch()} />
                  {revision.data && (
                    <>
                      {revision.data.items.slice(0, 5).map((item) => (
                        <div className="study-row" key={item.node_id}>
                          <h3>{item.node_name}</h3>
                          <p className="study-meta">
                            {item.paper_code} · Due {item.due_date}
                            {item.overdue_days > 0 ? ` · ${item.overdue_days} days overdue` : ""}
                          </p>
                          <Link
                            className="topic-link"
                            to={demoLink(`/revision?node=${encodeURIComponent(item.node_id)}`)}
                          >
                            Start revision
                          </Link>
                        </div>
                      ))}
                      {!revision.data.items.length && <p>Nothing is due for revision.</p>}
                    </>
                  )}
                </section>
                <section className="ledger-section">
                  <h2>Personal progress</h2>
                  {awaiting ? (
                    <p>Not available until this attempt’s syllabus is reviewed.</p>
                  ) : (
                    <>
                      <p className="ledger-figure">
                        <strong>{data.done_subtopics}</strong> / {data.total_subtopics} topics completed
                      </p>
                      <progress
                        className="study-bar"
                        aria-label="Personal syllabus progress"
                        max={data.total_subtopics || 1}
                        value={data.done_subtopics}
                      />
                    </>
                  )}
                  <Link className="topic-link" to={demoLink("/progress")}>
                    View progress
                  </Link>
                </section>
              </aside>
            </div>
            <section className="ledger-section">
              <h2>Recent activity</h2>
              {data.recent_activity.length ? (
                data.recent_activity.slice(0, 5).map((item, index) => (
                  <p className="study-row study-meta" key={`${item.node_id}-${index}`}>
                    {item.node_name} · {item.to_status.replace(/_/g, " ")} · {item.at}
                  </p>
                ))
              ) : (
                <p>No recent activity.</p>
              )}
            </section>
          </div>
        </>
      )}
    </div>
  );
}
