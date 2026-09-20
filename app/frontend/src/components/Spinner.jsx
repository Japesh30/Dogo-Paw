export default function Spinner({ label = 'Loading…' }) {
  return (
    <div className="flex flex-col items-center gap-3" role="status">
      <span className="border-olive-200 border-t-olive-500 h-9 w-9 animate-spin rounded-full border-4" />
      <span className="text-sm">{label}</span>
    </div>
  )
}
