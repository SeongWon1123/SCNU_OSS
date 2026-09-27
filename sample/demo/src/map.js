import { Map } from "react-kakao-maps-sdk";

navigator.geolocation.getCurrentPosition((pos) => {
  saveShopLocation(pos.coords.latitude, pos.coords.longitude);
});

export function ShopMap({ center }) {
  return <Map center={center} style={{ width: "100%", height: "360px" }} />;
}
