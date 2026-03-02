import Script from "next/script";
// TODO: 优化
export function SplashScreen() {
  return (
    <>
      {/* First-visit splash screen — covers unstyled content flash */}
      <div id="oops-splash">
        <div className="oops-splash__loader">
          <div className="oops-splash__circle"></div>
          <div className="oops-splash__text">
            {/* <span className="oops-splash__name">OopsNote</span> */}
            <span className="oops-splash__tip">加载中</span>
          </div>
        </div>
        <div className="oops-splash__section oops-splash__section--left"></div>
        <div className="oops-splash__section oops-splash__section--right"></div>
      </div>
      
      {/* Script to check localStorage and register dynamic dismiss callback */}
      <Script
        id="oopsnote-splash-init"
        strategy="beforeInteractive"
        src="/oopsnote-splash-init.js"
      />
    </>
  );
}
