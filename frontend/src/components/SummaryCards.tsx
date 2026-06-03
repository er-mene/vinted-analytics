interface Card {
  label: string;
  value: string | number;
}

export default function SummaryCards({ cards }: { cards: Card[] }) {
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-3.5 mb-6">
      {cards.map(({ label, value }) => (
        <div
          key={label}
          className="bg-panel/92 border border-line rounded-2xl shadow-[0_10px_30px_rgba(31,41,55,0.05)] backdrop-blur-sm px-4 py-4"
        >
          <div className="font-sans text-xs text-muted uppercase tracking-wider">
            {label}
          </div>
          <div className="mt-1.5 text-2xl font-bold">{value}</div>
        </div>
      ))}
    </div>
  );
}
