import 'styled-components';

declare module 'styled-components' {
  export interface StyleSheetManagerProps {
    shouldForwardProp?: (prop: string, elementToBeCreated: unknown) => boolean;
  }
}
