import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";

export interface ComboboxOption {
  name: string;
  count?: number;
}

interface ComboboxProps {
  id: string;
  value: string;
  onChange: (value: string) => void;
  options: ComboboxOption[];
  placeholder?: string;
  ariaLabel?: string;
  className?: string;
  required?: boolean;
}

export function Combobox({
  id,
  value,
  onChange,
  options,
  placeholder,
  ariaLabel,
  className,
  required,
}: ComboboxProps) {
  const listboxId = `${id}-listbox`;
  const wrapRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState(false);
  const [active, setActive] = useState(-1);

  const filtered = useMemo(() => {
    if (!typed) return options;
    const query = value.trim().toLowerCase();
    if (!query) return options;
    return options.filter((option) => option.name.toLowerCase().includes(query));
  }, [options, typed, value]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  const openList = () => {
    setOpen(true);
    setActive(filtered.length > 0 ? 0 : -1);
  };

  const select = (name: string) => {
    onChange(name);
    setTyped(false);
    setOpen(false);
    setActive(-1);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!open) {
        openList();
        return;
      }
      setActive((index) => (filtered.length === 0 ? -1 : (index + 1) % filtered.length));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) {
        openList();
        return;
      }
      setActive((index) =>
        filtered.length === 0 ? -1 : (index - 1 + filtered.length) % filtered.length,
      );
    } else if (event.key === "Enter") {
      if (open && filtered.length > 0) {
        event.preventDefault();
        select(filtered[active >= 0 ? active : 0].name);
      }
    } else if (event.key === "Escape") {
      if (open) {
        event.preventDefault();
        setOpen(false);
        setActive(-1);
      }
    } else if (event.key === "Tab") {
      setOpen(false);
    }
  };

  const activeId =
    open && active >= 0 && filtered[active] ? `${id}-opt-${active}` : undefined;

  return (
    <div ref={wrapRef} className="relative">
      <input
        id={id}
        role="combobox"
        aria-label={ariaLabel}
        aria-expanded={open}
        aria-controls={listboxId}
        aria-autocomplete="list"
        aria-activedescendant={activeId}
        aria-haspopup="listbox"
        autoComplete="off"
        value={value}
        required={required}
        placeholder={placeholder}
        className={className}
        onChange={(event) => {
          onChange(event.target.value);
          setTyped(true);
          setOpen(true);
          setActive(0);
        }}
        onFocus={() => {
          setTyped(false);
          openList();
        }}
        onClick={() => {
          setTyped(false);
          openList();
        }}
        onKeyDown={onKeyDown}
      />
      {open ? (
        <ul
          id={listboxId}
          role="listbox"
          aria-label={ariaLabel ? `${ariaLabel} suggestions` : undefined}
          className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-md border border-line bg-surface py-1 shadow-lg"
        >
          {filtered.length === 0 ? (
            <li role="presentation" className="px-3 py-2 text-xs text-muted">
              No matches. Your typed value will be kept.
            </li>
          ) : (
            filtered.map((option, index) => (
              <li
                key={option.name}
                id={`${id}-opt-${index}`}
                role="option"
                aria-selected={index === active}
                onMouseDown={(event) => {
                  event.preventDefault();
                  select(option.name);
                }}
                onMouseEnter={() => setActive(index)}
                className={`flex min-h-[40px] cursor-pointer items-center justify-between gap-2 px-3 text-sm ${
                  index === active ? "bg-raised text-mist" : "text-mist"
                }`}
              >
                <span className="truncate">{option.name}</span>
                {option.count != null ? (
                  <span className="font-mono text-xs text-muted">{option.count}</span>
                ) : null}
              </li>
            ))
          )}
        </ul>
      ) : null}
    </div>
  );
}
