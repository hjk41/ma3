import { render } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { UserContext } from '../src/contexts/UserContext';
const whoami = { principal:{principal_id:'user:alice',kind:'user',display_name:'Alice'}, via:'sso_cookie', libraries:[{library_id:'lib1', name:'Engineering', role:'admin', source:'acl'}], roles:[{scope_type:'library', scope_id:'lib1', role_name:'library_admin'}], admin_bypass:false };
export function renderWithUser(ui:any, user:any=whoami){ return render(<BrowserRouter><UserContext.Provider value={{whoami:user,reload:()=>{},loading:false}}>{ui}</UserContext.Provider></BrowserRouter>); }
export { whoami };
