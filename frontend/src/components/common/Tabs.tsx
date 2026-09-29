// 밑줄 인디케이터 탭 (NAME-F01) — docs/9-style-guide.md §5.7
import './Tabs.css';

export interface TabItem<T extends string> {
  value: T;
  label: string;
  count?: number;
}

interface TabsProps<T extends string> {
  items: TabItem<T>[];
  activeValue: T;
  onChange: (value: T) => void;
  label?: string;
}

export function Tabs<T extends string>({ items, activeValue, onChange, label }: TabsProps<T>) {
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {items.map((item) => (
        <button
          key={item.value}
          type="button"
          role="tab"
          aria-selected={item.value === activeValue}
          className={`tab ${item.value === activeValue ? 'is-active' : ''}`}
          onClick={() => onChange(item.value)}
        >
          {item.label}
          {typeof item.count === 'number' && <span className="tab__count">{item.count}</span>}
        </button>
      ))}
    </div>
  );
}
