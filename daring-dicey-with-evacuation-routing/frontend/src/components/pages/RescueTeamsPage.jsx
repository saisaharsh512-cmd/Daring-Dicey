import { severityMeta } from "../../severity";

export default function RescueTeamsPage({ result }) {
  if (!result) {
    return (
      <div className="page">
        <div className="panel empty-panel">
          <p>Run an analysis to generate AI rescue-team allocations.</p>
        </div>
      </div>
    );
  }

  const plan = result.rescue_allocation || {
    total_available_members: 0,
    total_allocated_members: 0,
    reserve_members: 0,
    num_teams: 0,
    teams: [],
    disclaimer: "No rescue allocation was returned.",
  };

  if (plan.total_available_members <= 0) {
    return (
      <div className="page">
        <section className="panel">
          <div className="panel__title">
            <h2>Rescue Team Allocation</h2>
            <p>Enter the total number of available rescue members before running the analysis.</p>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="page">
      <section className="panel">
        <div className="panel__title">
          <h2>AI Rescue Team Allocation</h2>
          <p>
            Available personnel are a pool, not a deployment target. Each affected
            location receives a bounded team based on severity and priority.
          </p>
        </div>

        <div className="rescue-summary-grid">
          <div className="kpi-card">
            <div className="kpi-card__label">Available</div>
            <div className="kpi-card__value">{plan.total_available_members}</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-card__label">Allocated</div>
            <div className="kpi-card__value">{plan.total_allocated_members}</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-card__label">Reserve</div>
            <div className="kpi-card__value">{plan.reserve_members}</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-card__label">Teams</div>
            <div className="kpi-card__value">{plan.num_teams}</div>
          </div>
        </div>

        {plan.teams.length === 0 ? (
          <p className="empty-note">No disaster-confirmed locations are available for rescue deployment.</p>
        ) : (
          <div className="rescue-team-list">
            {plan.teams.map((team) => {
              const meta = severityMeta(team.severity_level);
              return (
                <article key={team.team_id} className="rescue-team-card" style={{ "--rung-color": meta.color }}>
                  <div className="rescue-team-card__rail" />
                  <div className="rescue-team-card__body">
                    <div className="rescue-team-card__header">
                      <div>
                        <div className="rescue-team-card__name">{team.team_name}</div>
                        <div className="rescue-team-card__destination">
                          → {String(team.destination).replace("_", " ")}
                        </div>
                      </div>
                      <div className="rescue-team-card__members">
                        <strong>{team.members}</strong>
                        <span>members</span>
                      </div>
                    </div>

                    <div className="rescue-team-card__meta">
                      <span className="rescue-badge" style={{ color: meta.color }}>{team.severity_level}</span>
                      <span className="rescue-badge">{team.specialization}</span>
                      <span className="mono">Priority #{team.priority_rank}</span>
                    </div>

                    {team.hazards?.length > 0 && (
                      <div className="rescue-hazards">
                        {team.hazards.map((hazard) => <span className="tag" key={hazard}>{hazard}</span>)}
                      </div>
                    )}

                    <p className="rescue-team-card__reason">{team.reason}</p>
                    <div className="mono rescue-team-card__coords">
                      {Number(team.latitude).toFixed(5)}, {Number(team.longitude).toFixed(5)}
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}

        <p className="disclaimer-note">{plan.disclaimer}</p>
      </section>
    </div>
  );
}
