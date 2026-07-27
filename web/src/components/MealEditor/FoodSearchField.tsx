import { useId, useState } from "react";
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
 */
export default function FoodSearchField({ itemIndex, selectedName, onPick }: FoodSearchFieldProps): JSX.Element {
  const [query, setQuery] = useState(selectedName);
  const [isOpen, setIsOpen] = useState(false);
  const inputId = useId();
  const listboxId = useId();
  const { results, isLoading, isError } = useFoodSearch(query);

  const handlePick = (food: FoodSearchResult): void => {
    setQuery(food.name);
    setIsOpen(false);
    onPick(food);
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
        autoComplete="off"
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          setIsOpen(true);
        }}
        onFocus={() => setIsOpen(true)}
        onBlur={() => setIsOpen(false)}
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
            results.map((food) => (
              <li key={food.id} role="option" aria-selected={food.name === selectedName}>
                <button
                  type="button"
                  // onMouseDown (not onClick) fires before the input's onBlur closes the list.
                  onMouseDown={(event) => {
                    event.preventDefault();
                    handlePick(food);
                  }}
                  className="focus-ring flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-800"
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
