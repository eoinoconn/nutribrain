import { useId, useState, type KeyboardEvent } from "react";
import Skeleton from "../../design/Skeleton";
import type { FoodSearchResult } from "../../lib/api/types";
import { useFoodSearch } from "./useFoodSearch";

interface FoodSearchFieldProps {
  itemIndex: number;
  /** Currently picked food name, shown in the search box once a food is selected. */
  selectedName: string;
  onPick: (food: FoodSearchResult) => void;
}

/**
 * Debounced food search box for one item row. Shows a ★ marker for
 * favorites per spec §7 / G3. Purely a search-and-pick UI: it does not
 * resolve ambiguity beyond letting the user click a result (that's a
 * domain-layer concern per CLAUDE.md).
 *
 * Keyboard support (T-081 audit fix): this is a custom combobox — the only
 * one in the app beyond native `<select>`/`<input>` — so ArrowDown/ArrowUp
 * move a highlighted option, Enter picks the highlighted option, and Escape
 * closes the list without picking, matching `aria-activedescendant` combobox
 * conventions. Before this fix, results could only be picked with a mouse
 * (`onMouseDown` only), which failed the accessibility floor's requirement
 * that custom dropdown UI be keyboard-operable.
 */
export default function FoodSearchField({ itemIndex, selectedName, onPick }: FoodSearchFieldProps): JSX.Element {
  const [query, setQuery] = useState(selectedName);
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState<number>(-1);
  const inputId = useId();
  const listboxId = useId();
  const optionIdPrefix = useId();
  const { results, isLoading, isError } = useFoodSearch(query);

  const optionId = (index: number): string => `${optionIdPrefix}-option-${index}`;

  const handlePick = (food: FoodSearchResult): void => {
    setQuery(food.name);
    setIsOpen(false);
    setActiveIndex(-1);
    onPick(food);
  };

  const openList = (): void => {
    setIsOpen(true);
  };

  const closeList = (): void => {
    setIsOpen(false);
    setActiveIndex(-1);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>): void => {
    if (!isOpen || results.length === 0) {
      return;
    }
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        setActiveIndex((current) => (current + 1) % results.length);
        break;
      case "ArrowUp":
        event.preventDefault();
        setActiveIndex((current) => (current <= 0 ? results.length - 1 : current - 1));
        break;
      case "Enter":
        if (activeIndex >= 0 && activeIndex < results.length) {
          event.preventDefault();
          handlePick(results[activeIndex]!);
        }
        break;
      case "Escape":
        event.preventDefault();
        closeList();
        break;
      default:
        break;
    }
  };

  return (
    <div className="relative flex-1">
      <label htmlFor={inputId} className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
        Food (item {itemIndex + 1})
      </label>
      <input
        id={inputId}
        type="text"
        role="combobox"
        aria-expanded={isOpen}
        aria-controls={listboxId}
        aria-autocomplete="list"
        aria-activedescendant={isOpen && activeIndex >= 0 ? optionId(activeIndex) : undefined}
        autoComplete="off"
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          setActiveIndex(-1);
          openList();
        }}
        onFocus={openList}
        onBlur={closeList}
        onKeyDown={handleKeyDown}
        placeholder="Search foods..."
        className="focus-ring w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
      />
      {isOpen && query.trim().length > 0 ? (
        <ul
          id={listboxId}
          role="listbox"
          aria-label="Food search results"
          className="absolute z-10 mt-1 max-h-56 w-full overflow-auto rounded-md border border-slate-300 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900"
        >
          {isLoading ? (
            <li className="px-3 py-2">
              <Skeleton className="h-4 w-3/4" label="Loading food search results" />
            </li>
          ) : isError ? (
            <li className="px-3 py-2 text-sm text-red-600 dark:text-red-400">Food search failed. Try again.</li>
          ) : results.length === 0 ? (
            <li className="px-3 py-2 text-sm text-slate-500 dark:text-slate-400">No foods found.</li>
          ) : (
            results.map((food, index) => (
              <li
                key={food.id}
                id={optionId(index)}
                role="option"
                aria-selected={index === activeIndex || food.name === selectedName}
              >
                <button
                  type="button"
                  // onMouseDown (not onClick) fires before the input's onBlur closes the list.
                  onMouseDown={(event) => {
                    event.preventDefault();
                    handlePick(food);
                  }}
                  onMouseEnter={() => setActiveIndex(index)}
                  className={`focus-ring flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-800 ${
                    index === activeIndex ? "bg-slate-100 dark:bg-slate-800" : ""
                  }`}
                >
                  {food.isFavorite ? (
                    <span aria-label="Favorite" title="Favorite">
                      ★
                    </span>
                  ) : (
                    <span aria-hidden="true" className="inline-block w-[1em]" />
                  )}
                  <span>{food.name}</span>
                </button>
              </li>
            ))
          )}
        </ul>
      ) : null}
    </div>
  );
}
