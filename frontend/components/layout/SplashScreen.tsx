export function SplashScreen() {
  return (
    <div id="oops-splash" aria-hidden="true">
      <div className="oops-splash__loader">
        <div className="oops-splash__circle" />
        <div className="oops-splash__text">
          <span className="oops-splash__tip">加载中</span>
        </div>
      </div>
      <div className="oops-splash__section oops-splash__section--left" />
      <div className="oops-splash__section oops-splash__section--right" />
    </div>
  );
}
