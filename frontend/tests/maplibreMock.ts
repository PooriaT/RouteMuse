export class NavigationControl {}

export class Map {
  on() { return this; }
  addControl() { return this; }
  remove() {}
  isStyleLoaded() { return false; }
  getSource() { return undefined; }
  getLayer() { return undefined; }
  setFilter() {}
  getCanvas() { return document.createElement("canvas"); }
}

export default { Map, NavigationControl };
