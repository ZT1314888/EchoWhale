import type { SVGProps } from "react";

export type LogoProps = SVGProps<SVGSVGElement> & {
  title?: string;
};

export declare function Logo(props: LogoProps): React.JSX.Element;
