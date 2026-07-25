interface RadioOption<T extends string> {
  value: T;
  label: string;
  description?: string;
}

interface RadioGroupProps<T extends string> {
  name: string;
  label: string;
  description?: string;
  value: T;
  options: RadioOption<T>[];
  onChange: (value: T) => void;
  disabled?: boolean;
}

/** Wiederverwendbare Radio-Auswahl für den Einstellungen-Reiter, für
 * Einstellungen mit mehr als zwei Werten (siehe Toggle für den
 * An/Aus-Fall). */
export function RadioGroup<T extends string>({
  name,
  label,
  description,
  value,
  options,
  onChange,
  disabled,
}: RadioGroupProps<T>) {
  return (
    <div>
      <p className="text-sm font-medium text-slate-900">{label}</p>
      {description && <p className="mt-1 text-xs text-slate-500">{description}</p>}
      <div className="mt-3 space-y-3">
        {options.map((option) => (
          <label
            key={option.value}
            className="flex cursor-pointer items-start gap-2.5"
          >
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={value === option.value}
              disabled={disabled}
              onChange={() => onChange(option.value)}
              className="mt-0.5 h-4 w-4 shrink-0 border-slate-300 text-slate-900 focus:ring-slate-900 disabled:cursor-not-allowed disabled:opacity-50"
            />
            <span>
              <span className="text-sm text-slate-900">{option.label}</span>
              {option.description && (
                <span className="mt-0.5 block text-xs text-slate-500">
                  {option.description}
                </span>
              )}
            </span>
          </label>
        ))}
      </div>
    </div>
  );
}
