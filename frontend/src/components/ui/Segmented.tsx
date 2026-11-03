interface Props<T extends string> {
  value: T
  options: { value: T; label: string }[]
  onChange: (v: T) => void
  label: string
}

export function Segmented<T extends string>({ value, options, onChange, label }: Props<T>) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-lg bg-slate-100 p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${
            value === o.value ? 'bg-white text-navy-900 shadow-sm' : 'text-navy-500 hover:text-navy-800'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
