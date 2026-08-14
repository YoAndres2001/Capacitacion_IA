/**
 * Select con buscador integrado.
 *
 * Mantiene el aspecto del `TextField select` de siempre, pero cuando la lista
 * crece (proyectos, usuarios, capacitaciones…) agrega un campo de búsqueda
 * arriba del menú. Con pocas opciones el buscador estorba más de lo que ayuda,
 * así que solo aparece a partir de `searchThreshold`.
 */

import { Search } from '@mui/icons-material';
import { InputAdornment, ListSubheader, MenuItem, TextField, Typography } from '@mui/material';
import type { TextFieldProps } from '@mui/material';
import { useMemo, useState } from 'react';

export type SelectOption = {
  value: string;
  label: string;
  /** Texto secundario; también se considera al filtrar. */
  description?: string;
  disabled?: boolean;
};

type SearchableSelectProps = Omit<TextFieldProps, 'select' | 'value' | 'onChange'> & {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  /** Etiqueta de la opción vacía (por ejemplo «Todos»). Sin esto no se ofrece. */
  emptyLabel?: string;
  searchPlaceholder?: string;
  /** Cantidad de opciones a partir de la cual se muestra el buscador. */
  searchThreshold?: number;
};

const NO_RESULTS = '__no_results__';

export function SearchableSelect({
  value,
  onChange,
  options,
  emptyLabel,
  searchPlaceholder = 'Buscar…',
  searchThreshold = 6,
  SelectProps,
  ...textFieldProps
}: SearchableSelectProps) {
  const [query, setQuery] = useState('');

  const withSearch = options.length >= searchThreshold;

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return options;
    return options.filter((option) =>
      `${option.label} ${option.description ?? ''}`.toLowerCase().includes(needle),
    );
  }, [options, query]);

  // El valor seleccionado se pinta desde `options`, no desde el `MenuItem`: al
  // filtrar, el elegido puede no estar renderizado y el campo se vería vacío.
  const renderValue = (selected: unknown) => {
    const current = String(selected ?? '');
    if (!current) return emptyLabel ?? '';
    return options.find((option) => option.value === current)?.label ?? '';
  };

  return (
    <TextField
      select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      {...textFieldProps}
      // Con `emptyLabel` el campo nunca se ve vacío (muestra «Todos»), pero MUI
      // solo encoge la etiqueta cuando hay valor: sin esto se superponen. El
      // `shrink` además abre la muesca del borde, que se calcula a partir de él.
      InputLabelProps={
        emptyLabel
          ? { shrink: true, ...textFieldProps.InputLabelProps }
          : textFieldProps.InputLabelProps
      }
      SelectProps={{
        displayEmpty: Boolean(emptyLabel),
        renderValue,
        ...SelectProps,
        MenuProps: {
          // El menú no debe capturar el foco: lo necesita el buscador.
          autoFocus: false,
          PaperProps: { sx: { maxHeight: 360 } },
          ...SelectProps?.MenuProps,
        },
        onClose: (event) => {
          setQuery('');
          SelectProps?.onClose?.(event);
        },
      }}
    >
      {withSearch && (
        <ListSubheader sx={{ p: 1, bgcolor: 'background.paper', lineHeight: 'normal' }}>
          <TextField
            autoFocus
            size="small"
            placeholder={searchPlaceholder}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            // Sin esto el Select interpreta cada tecla como salto rápido a una
            // opción y roba el texto que se está escribiendo.
            onKeyDown={(event) => {
              if (event.key !== 'Escape') event.stopPropagation();
            }}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <Search fontSize="small" />
                </InputAdornment>
              ),
            }}
          />
        </ListSubheader>
      )}

      {emptyLabel && (
        <MenuItem value="" sx={query.trim() ? { display: 'none' } : undefined}>
          {emptyLabel}
        </MenuItem>
      )}

      {/* La opción elegida se mantiene montada aunque el filtro la descarte:
          si desaparece, el Select la trata como valor fuera de rango. */}
      {Boolean(value) && !filtered.some((option) => option.value === value) && (
        <MenuItem value={value} sx={{ display: 'none' }}>
          {renderValue(value)}
        </MenuItem>
      )}

      {filtered.map((option) => (
        <MenuItem key={option.value} value={option.value} disabled={option.disabled}>
          {option.description ? (
            <span>
              {option.label}
              <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }}>
                {option.description}
              </Typography>
            </span>
          ) : (
            option.label
          )}
        </MenuItem>
      ))}

      {filtered.length === 0 && (
        <MenuItem value={NO_RESULTS} disabled>
          Sin coincidencias
        </MenuItem>
      )}
    </TextField>
  );
}
