// Knowledge graph — static screenshot of the live cockpit graph view.
// Mirrors the same `<img>`-based pattern used by the Bullseye demo on
// the landing so the section reads as a real product preview.
export function LandingGraphDive() {
  return (
    <section className="kg-section">
      <div className="kg-text">
        <div className="ix">KNOWLEDGE GRAPH</div>
        <h3>Every fact, linked.</h3>
        <p>
          Drugs, targets, mechanisms, companies, indications — every entity
          in your franchise wired into a living graph.
        </p>
      </div>

      <div className="kg-stage">
        <img
          className="kg-snapshot"
          src="/snapshots/graph.png"
          alt="Knowledge graph — pharma franchise entities and relationships"
          loading="lazy"
        />
      </div>
    </section>
  );
}
