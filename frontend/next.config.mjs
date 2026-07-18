/** @type {import('next').NextConfig} */
const nextConfig = {
  // react-leaflet은 개발 StrictMode의 이중 마운트에서 "Map container is already
  // initialized"를 던진다. 지도 컴포넌트가 마운트별 고유 key로 새 DOM을 쓰도록
  // 했지만, 개발 모드의 이중 호출 노이즈까지 없애기 위해 StrictMode를 끈다.
  reactStrictMode: false,
};

export default nextConfig;
