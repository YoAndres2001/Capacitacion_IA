import { createContext, useContext } from 'react';

export type ColorMode = 'light' | 'dark';

export const ColorModeContext = createContext<{ mode: ColorMode; toggle: () => void }>({
  mode: 'light',
  toggle: () => undefined,
});

export const useColorMode = () => useContext(ColorModeContext);
