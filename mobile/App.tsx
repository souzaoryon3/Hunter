import React from 'react';
import { ActivityIndicator, Text, View } from 'react-native';
import { NavigationContainer, DefaultTheme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { SafeAreaProvider, useSafeAreaInsets } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { AppProvider, useApp } from './src/context/AppProvider';
import type { RootStackParams, TabParams } from './src/navigation/types';
import { CatalogScreen } from './src/screens/CatalogScreen';
import { AlertsScreen, AlertFormScreen } from './src/screens/AlertScreens';
import { NotificationsScreen } from './src/screens/NotificationsScreen';
import { AccountScreen, AuthScreen, ConnectionScreen, ProfileScreen } from './src/screens/AccountScreens';
import { ProductScreen } from './src/screens/ProductScreen';
import { Icon, type IconName } from './src/ui/components';
import { colors } from './src/ui/theme';

const Stack = createNativeStackNavigator<RootStackParams>();
const Tabs = createBottomTabNavigator<TabParams>();
const icons: Record<keyof TabParams, IconName> = { Offers: 'view-grid-outline', Alerts: 'radar', Notifications: 'bell-outline', Account: 'account-outline' };
const theme = { ...DefaultTheme, colors: { ...DefaultTheme.colors, background: colors.paper, card: colors.white, primary: colors.green, text: colors.ink, border: colors.line, notification: colors.green } };

function MainTabs() {
  const insets = useSafeAreaInsets();
  return <Tabs.Navigator screenOptions={({ route }) => ({ headerShown: false,
    tabBarActiveTintColor: colors.green, tabBarInactiveTintColor: colors.muted,
    tabBarStyle: { height: 66 + Math.max(insets.bottom, 8), paddingTop: 8, paddingBottom: Math.max(insets.bottom, 8), borderTopColor: colors.line },
    tabBarLabelStyle: { fontSize: 11, fontWeight: '600' },
    tabBarIcon: ({ focused, color }) => <View style={{ paddingVertical: 4, paddingHorizontal: 15, borderRadius: 20, backgroundColor: focused ? colors.lime : 'transparent' }}><Icon name={icons[route.name]} color={color} size={23} /></View>,
  })}>
    <Tabs.Screen name="Offers" component={CatalogScreen} options={{ title: 'Ofertas' }} />
    <Tabs.Screen name="Alerts" component={AlertsScreen} options={{ title: 'Alertas' }} />
    <Tabs.Screen name="Notifications" component={NotificationsScreen} options={{ title: 'Notificações' }} />
    <Tabs.Screen name="Account" component={AccountScreen} options={{ title: 'Conta' }} />
  </Tabs.Navigator>;
}

function Navigator() {
  const { ready, endpoint } = useApp();
  if (!ready) return <View style={{ flex: 1, backgroundColor: colors.paper, alignItems: 'center', justifyContent: 'center', gap: 16 }}><Icon name="radar" size={48} color={colors.green} /><Text style={{ color: colors.ink, fontSize: 30, fontWeight: '800' }}>hunter.</Text><ActivityIndicator color={colors.green} /></View>;
  return <NavigationContainer theme={theme}>
    <Stack.Navigator key={endpoint || 'unconfigured'} screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.paper } }}>
      <Stack.Screen name="Main" component={MainTabs} />
      <Stack.Screen name="Product" component={ProductScreen} />
      <Stack.Screen name="Auth" component={AuthScreen} options={{ presentation: 'modal' }} />
      <Stack.Screen name="AlertForm" component={AlertFormScreen} options={{ presentation: 'modal' }} />
      <Stack.Screen name="Profile" component={ProfileScreen} />
      <Stack.Screen name="Connection" component={ConnectionScreen} />
    </Stack.Navigator>
  </NavigationContainer>;
}

export default function App() {
  return <SafeAreaProvider><StatusBar style="dark" /><AppProvider><Navigator /></AppProvider></SafeAreaProvider>;
}
