import { MD3DarkTheme, MD3LightTheme } from "react-native-paper";

export const lightTheme = {
  ...MD3LightTheme,
  colors: {
    ...MD3LightTheme.colors,
    primary: "#9B3E20",
    onPrimary: "#FFFFFF",
    primaryContainer: "#FFDBCD",
    onPrimaryContainer: "#380D00",
    secondary: "#506443",
    background: "#FFF8F3",
    surface: "#FFF8F3",
  },
};
export const darkTheme = {
  ...MD3DarkTheme,
  colors: {
    ...MD3DarkTheme.colors,
    primary: "#FFB59A",
    onPrimary: "#5B1B06",
    primaryContainer: "#7A2B0E",
    onPrimaryContainer: "#FFDBCD",
    secondary: "#B7CDA6",
  },
};
