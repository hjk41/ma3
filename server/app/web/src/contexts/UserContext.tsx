import { createContext, useContext } from 'react';
import type { Whoami } from '../api/client';
export const UserContext = createContext<{ whoami: Whoami | null; reload: () => void; loading: boolean }>({ whoami: null, reload: () => {}, loading: false });
export const useUser = () => useContext(UserContext);
